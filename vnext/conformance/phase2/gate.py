"""Minimal P2-PR-STATIC gate entry for Phase 2 affected-scope routing."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import threading
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, BinaryIO, Literal

from gateway_conformance.errors import ConformanceValidationError
from gateway_conformance.sanitize import sanitize_message

from router import (
    Inventory,
    PathChange,
    RouterError,
    RouterErrorCode,
    RoutingResult,
    load_inventory,
    route_changes,
)

GATE_COMMAND_SCHEMA_VERSION = 1
GATE_RESULT_SCHEMA_VERSION = 1
ACTIVE_STATIC_GATE_NAME = "P2-PR-STATIC"
DIAGNOSTIC_TAIL_BYTES = 4096
TRUNCATION_MARKER = "...[truncated]..."

_COMMAND_KEYS = frozenset({"schema_version", "command", "changes", "repo_root", "static_checks"})
_CHANGE_KEYS = frozenset({"path", "status", "old_path"})

GateOutcomeStatus = Literal[
    "PASS",
    "FAIL",
    "BLOCKED",
    "NOT_EXECUTED",
    "DELEGATED",
]


class StaticStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"


class RoutingStatus(StrEnum):
    ROUTED = "ROUTED"


class RevisionClosure(StrEnum):
    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"


@dataclass(frozen=True, slots=True)
class GateCommand:
    schema_version: int
    command: Literal["route", "execute"]
    changes: tuple[PathChange, ...]
    repo_root: Path
    static_checks: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class GateOutcome:
    gate: str
    activation: str
    status: GateOutcomeStatus


@dataclass(frozen=True, slots=True)
class RoutingView:
    schema_version: int
    selected_gates: tuple[str, ...]
    gate_activation: tuple[tuple[str, str], ...]
    diagnostics: tuple[str, ...]
    fail_closed: bool
    narrow_scope: bool
    pending_external_gates: tuple[str, ...]
    pending_inactive_gates: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class GateResult:
    schema_version: int
    command: Literal["route", "execute"]
    routing: RoutingView
    gate_outcomes: tuple[GateOutcome, ...]
    diagnostics: tuple[str, ...]
    pending_external_gates: tuple[str, ...]
    pending_inactive_gates: tuple[str, ...]
    routing_status: RoutingStatus | None = None
    static_status: StaticStatus | None = None
    revision_closure: RevisionClosure | None = None


@dataclass(frozen=True, slots=True)
class StaticCheck:
    check_id: str
    cwd: Path
    argv: tuple[str, ...]


def _repo_root_from_default() -> Path:
    return Path(__file__).resolve().parents[3]


def _require_closed_keys(raw: dict[str, Any], allowed: frozenset[str], *, label: str) -> None:
    unknown = set(raw) - allowed
    if unknown:
        raise RouterError(
            RouterErrorCode.UNKNOWN_FIELD,
            detail=f"{label}:{','.join(sorted(unknown))}",
        )


def _parse_changes(raw_changes: list[dict[str, Any]]) -> list[PathChange]:
    parsed: list[PathChange] = []
    for index, entry in enumerate(raw_changes):
        if not isinstance(entry, dict):
            raise RouterError(RouterErrorCode.INVALID_INVENTORY, detail="change")
        _require_closed_keys(entry, _CHANGE_KEYS, label=f"change[{index}]")
        path = entry.get("path")
        status = entry.get("status")
        if not isinstance(path, str) or not isinstance(status, str):
            raise RouterError(RouterErrorCode.INVALID_INVENTORY, detail="change_fields")
        if status not in {
            "added",
            "modified",
            "deleted",
            "renamed",
            "copied",
            "type_changed",
        }:
            raise RouterError(RouterErrorCode.UNKNOWN_CHANGE_STATUS, detail=status)
        old_path = entry.get("old_path")
        if old_path is not None and not isinstance(old_path, str):
            raise RouterError(RouterErrorCode.INVALID_INVENTORY, detail="old_path")
        parsed.append(PathChange(path=path, status=status, old_path=old_path))  # type: ignore[arg-type]
    return parsed


def parse_gate_command(payload: dict[str, Any]) -> GateCommand:
    if not isinstance(payload, dict):
        raise RouterError(RouterErrorCode.INVALID_INVENTORY, detail="command")
    _require_closed_keys(payload, _COMMAND_KEYS, label="command")

    schema_version = payload.get("schema_version")
    if schema_version != GATE_COMMAND_SCHEMA_VERSION:
        raise RouterError(RouterErrorCode.SCHEMA_MISMATCH, detail="command_schema_version")

    command = payload.get("command")
    if command not in {"route", "execute"}:
        raise RouterError(RouterErrorCode.INVALID_INVENTORY, detail="command")

    changes_raw = payload.get("changes")
    if not isinstance(changes_raw, list):
        raise RouterError(RouterErrorCode.INVALID_INVENTORY, detail="changes")

    repo_root_raw = payload.get("repo_root", ".")
    if not isinstance(repo_root_raw, str):
        raise RouterError(RouterErrorCode.INVALID_INVENTORY, detail="repo_root")
    repo_root = Path(repo_root_raw).resolve()

    static_checks_raw = payload.get("static_checks", [])
    if not isinstance(static_checks_raw, list):
        raise RouterError(RouterErrorCode.INVALID_INVENTORY, detail="static_checks")
    static_checks = tuple(str(item) for item in static_checks_raw)

    return GateCommand(
        schema_version=GATE_COMMAND_SCHEMA_VERSION,
        command=command,
        changes=tuple(_parse_changes(changes_raw)),
        repo_root=repo_root,
        static_checks=static_checks,
    )


def routing_view_from_result(routing: RoutingResult) -> RoutingView:
    return RoutingView(
        schema_version=routing.schema_version,
        selected_gates=routing.selected_gates,
        gate_activation=routing.gate_activation,
        diagnostics=routing.diagnostics,
        fail_closed=routing.fail_closed,
        narrow_scope=routing.narrow_scope,
        pending_external_gates=routing.pending_external_gates,
        pending_inactive_gates=routing.pending_inactive_gates,
    )


def gate_result_to_dict(result: GateResult) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": result.schema_version,
        "command": result.command,
        "routing": {
            "schema_version": result.routing.schema_version,
            "selected_gates": list(result.routing.selected_gates),
            "gate_activation": dict(result.routing.gate_activation),
            "diagnostics": list(result.routing.diagnostics),
            "fail_closed": result.routing.fail_closed,
            "narrow_scope": result.routing.narrow_scope,
            "pending_external_gates": list(result.routing.pending_external_gates),
            "pending_inactive_gates": list(result.routing.pending_inactive_gates),
        },
        "gate_outcomes": [
            {
                "gate": outcome.gate,
                "activation": outcome.activation,
                "status": outcome.status,
            }
            for outcome in result.gate_outcomes
        ],
        "pending_external_gates": list(result.pending_external_gates),
        "pending_inactive_gates": list(result.pending_inactive_gates),
        "diagnostics": list(result.diagnostics),
    }
    if result.routing_status is not None:
        payload["routing_status"] = result.routing_status.value
    if result.static_status is not None:
        payload["static_status"] = result.static_status.value
    if result.revision_closure is not None:
        payload["revision_closure"] = result.revision_closure.value
    return payload


def _outcomes_for_routing(routing: RoutingView, inventory: Inventory) -> list[GateOutcome]:
    outcomes: list[GateOutcome] = []
    for gate in routing.selected_gates:
        activation = inventory.gate_activation(gate)
        if activation == "active":
            status: GateOutcomeStatus = "NOT_EXECUTED"
        elif activation == "inactive":
            status = "NOT_EXECUTED"
        else:
            status = "DELEGATED"
        outcomes.append(GateOutcome(gate=gate, activation=activation, status=status))
    return outcomes


def _git_command(repo_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo_root), *args],
        check=False,
        capture_output=True,
        text=True,
    )


def _git_command_bytes(repo_root: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", "-C", str(repo_root), *args],
        check=False,
        capture_output=True,
    )


def _split_nul_records(raw: bytes) -> tuple[str, ...]:
    if not raw:
        return ()
    return tuple(
        record.decode("utf-8", errors="surrogateescape") for record in raw.split(b"\0") if record
    )


def _tracked_worktree_snapshot(repo_root: Path) -> tuple[tuple[str, ...], str | None]:
    status_proc = _git_command_bytes(
        repo_root,
        "status",
        "--porcelain=v2",
        "-z",
        "--untracked-files=no",
    )
    if status_proc.returncode != 0:
        return (), "worktree_snapshot_failed"

    ls_files_proc = _git_command_bytes(repo_root, "ls-files", "-z")
    if ls_files_proc.returncode != 0:
        return (), "worktree_snapshot_failed"

    lines = [f"status:{record}" for record in _split_nul_records(status_proc.stdout)]
    for relative_path in sorted(_split_nul_records(ls_files_proc.stdout)):
        entry_path = repo_root / relative_path
        if os.path.lexists(entry_path):
            if entry_path.is_symlink():
                lines.append(f"content:{relative_path}:symlink:{os.readlink(entry_path)}")
            else:
                hash_proc = _git_command(repo_root, "hash-object", "--", relative_path)
                if hash_proc.returncode != 0:
                    return (), "worktree_snapshot_failed"
                object_id = hash_proc.stdout.strip()
                if not object_id:
                    return (), "worktree_snapshot_failed"
                lines.append(f"content:{relative_path}:{object_id}")
        else:
            lines.append(f"content:{relative_path}:deleted")

    return tuple(sorted(lines)), None


def _worktree_unchanged(
    repo_root: Path,
    before: tuple[str, ...],
) -> tuple[bool, str | None]:
    after, error = _tracked_worktree_snapshot(repo_root)
    if error is not None:
        return False, error
    return before == after, None


def _bounded_stream_tail(data: str) -> str:
    if len(data) <= DIAGNOSTIC_TAIL_BYTES:
        return str(sanitize_message(data))
    truncated = data[-DIAGNOSTIC_TAIL_BYTES:]
    return str(sanitize_message(f"{TRUNCATION_MARKER}{truncated}"))


def _bounded_process_output(stdout: str, stderr: str) -> tuple[str, str]:
    return _bounded_stream_tail(stdout), _bounded_stream_tail(stderr)


class _BytesRingBufferTail:
    def __init__(self, capacity: int) -> None:
        self._capacity = capacity
        self._buffer = b""

    def append(self, data: bytes) -> None:
        if not data:
            return
        combined = self._buffer + data
        if len(combined) > self._capacity:
            self._buffer = combined[-self._capacity :]
        else:
            self._buffer = combined

    def value_text(self) -> str:
        return self._buffer.decode("utf-8", errors="replace")


def _drain_stream_to_tail(stream: BinaryIO, tail: _BytesRingBufferTail) -> None:
    while True:
        chunk = stream.read(4096)
        if not chunk:
            break
        tail.append(chunk)


def _drain_stream_to_tail_safe(
    stream: BinaryIO,
    tail: _BytesRingBufferTail,
    errors: list[BaseException],
) -> None:
    try:
        _drain_stream_to_tail(stream, tail)
    except BaseException as exc:  # noqa: BLE001 - propagate drain failures to caller
        errors.append(exc)


def _run_subprocess(
    argv: tuple[str, ...],
    *,
    cwd: Path,
    env: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    proc = subprocess.Popen(
        list(argv),
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert proc.stdout is not None
    assert proc.stderr is not None
    stdout_tail = _BytesRingBufferTail(DIAGNOSTIC_TAIL_BYTES * 2)
    stderr_tail = _BytesRingBufferTail(DIAGNOSTIC_TAIL_BYTES * 2)
    drain_errors: list[BaseException] = []
    stdout_thread = threading.Thread(
        target=_drain_stream_to_tail_safe,
        args=(proc.stdout, stdout_tail, drain_errors),
        daemon=True,
    )
    stderr_thread = threading.Thread(
        target=_drain_stream_to_tail_safe,
        args=(proc.stderr, stderr_tail, drain_errors),
        daemon=True,
    )
    stdout_thread.start()
    stderr_thread.start()
    stdout_thread.join()
    stderr_thread.join()
    returncode = proc.wait()
    if drain_errors:
        raise drain_errors[0]
    return subprocess.CompletedProcess(
        list(argv),
        returncode,
        stdout_tail.value_text(),
        stderr_tail.value_text(),
    )


def _format_check_detail(check_id: str, stdout: str, stderr: str) -> str | None:
    bounded_stdout, bounded_stderr = _bounded_process_output(stdout, stderr)
    parts: list[str] = []
    if bounded_stdout:
        parts.append(f"stdout={bounded_stdout}")
    if bounded_stderr:
        parts.append(f"stderr={bounded_stderr}")
    if not parts:
        return None
    return f"detail:{check_id}:{';'.join(parts)}"


def _base_env() -> dict[str, str]:
    env = os.environ.copy()
    for inherited in ("PYTHONHOME", "PYTHONPATH", "VIRTUAL_ENV"):
        env.pop(inherited, None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.setdefault("UV_CACHE_DIR", str(Path.home() / ".cache" / "uv"))
    review_tmp = env.get("REVIEW_TMP")
    if review_tmp:
        env.setdefault("UV_PROJECT_ENVIRONMENT", str(Path(review_tmp) / "venv-conformance"))
        env.setdefault("RUFF_CACHE_DIR", str(Path(review_tmp) / "ruff-cache"))
        env.setdefault("MYPY_CACHE_DIR", str(Path(review_tmp) / "mypy-cache"))
    return env


def _command_exists(command: str) -> bool:
    return shutil.which(command) is not None


def _path_hits_prefix(path: str, prefix: str) -> bool:
    normalized_prefix = prefix.rstrip("/")
    return path == normalized_prefix or path.startswith(f"{normalized_prefix}/")


def _static_checks_for_routing(
    routing: RoutingView,
    repo_root: Path,
    changed_paths: tuple[str, ...],
) -> list[StaticCheck]:
    conformance_root = repo_root / "vnext" / "conformance"
    checks: list[StaticCheck] = []

    run_static = (
        ACTIVE_STATIC_GATE_NAME in routing.selected_gates
        or routing.narrow_scope
        or any(_path_hits_prefix(path, "vnext/conformance/phase2/") for path in changed_paths)
    )
    if run_static:
        python = sys.executable
        checks.extend(
            [
                StaticCheck(
                    "static.ruff", conformance_root, (python, "-m", "ruff", "check", "phase2")
                ),
                StaticCheck("static.mypy", conformance_root, (python, "-m", "mypy", "phase2")),
                StaticCheck(
                    "static.pytest",
                    conformance_root,
                    (
                        python,
                        "-m",
                        "pytest",
                        "-q",
                        "-p",
                        "no:cacheprovider",
                        "-m",
                        "not nested_cli",
                        "phase2/tests",
                    ),
                ),
                StaticCheck(
                    "static.closure",
                    conformance_root,
                    (
                        python,
                        str(conformance_root / "phase2" / "closure.py"),
                        "validate",
                        "--repo-root",
                        str(repo_root),
                    ),
                ),
                StaticCheck(
                    "static.lock.conformance",
                    conformance_root,
                    ("uv", "lock", "--check", "--offline"),
                ),
            ]
        )

    repository_prefixes = (
        "vnext/repository_contracts/",
        "vnext/repository_client/",
        "vnext/repository_service/",
    )
    repository_hit = (
        any(
            _path_hits_prefix(path, prefix)
            for path in changed_paths
            for prefix in repository_prefixes
        )
        or "vnext/repository-workspace.toml" in changed_paths
    )
    if repository_hit:
        for project in ("repository_contracts", "repository_client", "repository_service"):
            project_root = repo_root / "vnext" / project
            checks.append(
                StaticCheck(
                    f"static.lock.repository.{project}",
                    project_root,
                    ("uv", "lock", "--check", "--offline"),
                )
            )
        checks.append(
            StaticCheck(
                "static.boundary.repository",
                repo_root / "vnext" / "repository_service",
                (
                    "uv",
                    "run",
                    "--offline",
                    "--no-sync",
                    "pytest",
                    "-q",
                    "-p",
                    "no:cacheprovider",
                    "tests/test_distribution_boundaries.py",
                ),
            )
        )

    return checks


def _execute_static_checks(
    checks: list[StaticCheck],
    *,
    extra_checks: tuple[str, ...],
) -> tuple[StaticStatus, tuple[str, ...]]:
    if checks and not _command_exists(sys.executable):
        return StaticStatus.BLOCKED, ("python_unavailable",)
    if any(check.argv[0] == "uv" for check in checks) and not _command_exists("uv"):
        return StaticStatus.BLOCKED, ("uv_unavailable",)

    env = _base_env()
    diagnostics: list[str] = []

    for fail_marker in extra_checks:
        diagnostics.append("check:static.injected:exit=1")
        return StaticStatus.FAIL, tuple(sorted(diagnostics))

    for check in checks:
        check_env = env
        if any(isinstance(arg, str) and "phase2/closure.py" in arg for arg in check.argv):
            check_env = env.copy()
            check_env["PYTHONPATH"] = os.pathsep.join(
                [str(check.cwd / "src"), str(check.cwd / "phase2")]
            )
        proc = _run_subprocess(check.argv, cwd=check.cwd, env=check_env)
        diagnostics.append(f"check:{check.check_id}:exit={proc.returncode}")
        if proc.returncode != 0:
            detail = _format_check_detail(check.check_id, proc.stdout, proc.stderr)
            if detail:
                diagnostics.append(detail)
            if proc.returncode < 0:
                return StaticStatus.FAIL, tuple(sorted(diagnostics))
            return StaticStatus.FAIL, tuple(sorted(diagnostics))

    return StaticStatus.PASS, tuple(sorted(diagnostics))


def _revision_closure_for(
    routing: RoutingView,
    static_status: StaticStatus,
) -> RevisionClosure:
    if static_status is not StaticStatus.PASS:
        return RevisionClosure.INCOMPLETE
    if routing.pending_external_gates or routing.pending_inactive_gates:
        return RevisionClosure.INCOMPLETE
    return RevisionClosure.COMPLETE


def _error_routing_view(inv: Inventory, diagnostic: str) -> RoutingView:
    return RoutingView(
        schema_version=inv.schema_version,
        selected_gates=(),
        gate_activation=(),
        diagnostics=(diagnostic,),
        fail_closed=True,
        narrow_scope=False,
        pending_external_gates=(),
        pending_inactive_gates=(),
    )


def run_gate_command(command: GateCommand, inventory: Inventory | None = None) -> GateResult:
    inv = inventory or load_inventory()
    diagnostics: list[str] = []

    try:
        routing_result = route_changes(list(command.changes), inv)
        routing = routing_view_from_result(routing_result)
    except RouterError as exc:
        routing = _error_routing_view(inv, exc.code.value)
        return GateResult(
            schema_version=GATE_RESULT_SCHEMA_VERSION,
            command=command.command,
            routing=routing,
            gate_outcomes=(),
            diagnostics=(exc.code.value,),
            pending_external_gates=(),
            pending_inactive_gates=(),
            routing_status=None,
            static_status=StaticStatus.FAIL if command.command == "execute" else None,
            revision_closure=RevisionClosure.INCOMPLETE if command.command == "execute" else None,
        )

    outcomes = _outcomes_for_routing(routing, inv)
    changed_paths: set[str] = set()
    for change in command.changes:
        changed_paths.add(change.path)
        if change.old_path is not None:
            changed_paths.add(change.old_path)
    changed_paths_tuple = tuple(sorted(changed_paths))

    if command.command == "route":
        return GateResult(
            schema_version=GATE_RESULT_SCHEMA_VERSION,
            command="route",
            routing=routing,
            gate_outcomes=tuple(outcomes),
            diagnostics=tuple(sorted(diagnostics)),
            pending_external_gates=routing.pending_external_gates,
            pending_inactive_gates=routing.pending_inactive_gates,
            routing_status=RoutingStatus.ROUTED,
            static_status=None,
            revision_closure=None,
        )

    before_snapshot, snapshot_error = _tracked_worktree_snapshot(command.repo_root)
    if snapshot_error is not None:
        return GateResult(
            schema_version=GATE_RESULT_SCHEMA_VERSION,
            command="execute",
            routing=routing,
            gate_outcomes=tuple(outcomes),
            diagnostics=(snapshot_error,),
            pending_external_gates=routing.pending_external_gates,
            pending_inactive_gates=routing.pending_inactive_gates,
            routing_status=None,
            static_status=StaticStatus.BLOCKED,
            revision_closure=RevisionClosure.INCOMPLETE,
        )

    static_status = StaticStatus.PASS
    checks = _static_checks_for_routing(routing, command.repo_root, changed_paths_tuple)
    if checks or command.static_checks:
        static_status, static_diagnostics = _execute_static_checks(
            checks,
            extra_checks=command.static_checks,
        )
        diagnostics.extend(static_diagnostics)
    elif ACTIVE_STATIC_GATE_NAME not in routing.selected_gates:
        static_status = StaticStatus.FAIL
        diagnostics.append("missing_required_static_check")

    unchanged, worktree_error = _worktree_unchanged(command.repo_root, before_snapshot)
    if worktree_error is not None:
        diagnostics.append(worktree_error)
        static_status = StaticStatus.BLOCKED
    elif not unchanged:
        diagnostics.append("tracked_worktree_mutated")
        static_status = StaticStatus.FAIL

    updated_outcomes: list[GateOutcome] = []
    for outcome in outcomes:
        if outcome.gate == ACTIVE_STATIC_GATE_NAME and outcome.activation == "active":
            if static_status is StaticStatus.PASS:
                status: GateOutcomeStatus = "PASS"
            elif static_status is StaticStatus.BLOCKED:
                status = "BLOCKED"
            else:
                status = "FAIL"
            updated_outcomes.append(
                GateOutcome(gate=outcome.gate, activation=outcome.activation, status=status)
            )
        else:
            updated_outcomes.append(outcome)

    if routing.narrow_scope and ACTIVE_STATIC_GATE_NAME not in routing.selected_gates:
        if static_status is StaticStatus.PASS:
            narrow_status: GateOutcomeStatus = "PASS"
        elif static_status is StaticStatus.BLOCKED:
            narrow_status = "BLOCKED"
        else:
            narrow_status = "FAIL"
        updated_outcomes.append(
            GateOutcome(
                gate=ACTIVE_STATIC_GATE_NAME,
                activation=inv.gate_activation(ACTIVE_STATIC_GATE_NAME),
                status=narrow_status,
            )
        )

    if any(
        outcome.status == "PASS" for outcome in updated_outcomes if outcome.activation != "active"
    ):
        static_status = StaticStatus.FAIL
        diagnostics.append("inactive_gate_pass_forbidden")

    revision_closure = _revision_closure_for(routing, static_status)

    return GateResult(
        schema_version=GATE_RESULT_SCHEMA_VERSION,
        command="execute",
        routing=routing,
        gate_outcomes=tuple(updated_outcomes),
        diagnostics=tuple(sorted(set(diagnostics))),
        pending_external_gates=routing.pending_external_gates,
        pending_inactive_gates=routing.pending_inactive_gates,
        routing_status=None,
        static_status=static_status,
        revision_closure=revision_closure,
    )


def _exit_code_for_result(result: GateResult) -> int:
    if result.command == "route":
        return 0 if result.routing_status is RoutingStatus.ROUTED else 1
    if result.static_status is StaticStatus.BLOCKED:
        return 3
    if result.static_status is StaticStatus.FAIL:
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 2 affected-scope gate entry")
    parser.add_argument("command", choices=["route", "execute"])
    parser.add_argument("--changes-json", required=True)
    parser.add_argument("--repo-root", default=str(_repo_root_from_default()))
    args = parser.parse_args(argv)

    try:
        changes_payload = json.loads(args.changes_json)
    except json.JSONDecodeError:
        print(json.dumps({"error": "invalid_json"}))
        return 1

    if not isinstance(changes_payload, list):
        print(json.dumps({"error": "changes_must_be_list"}))
        return 1

    payload = {
        "schema_version": GATE_COMMAND_SCHEMA_VERSION,
        "command": args.command,
        "changes": changes_payload,
        "repo_root": args.repo_root,
    }
    try:
        command = parse_gate_command(payload)
        result = run_gate_command(command)
    except RouterError as exc:
        print(json.dumps({"error": exc.code.value}))
        return 1
    except ConformanceValidationError:
        print(json.dumps({"error": RouterErrorCode.INVALID_INVENTORY.value}))
        return 1

    print(json.dumps(gate_result_to_dict(result), sort_keys=True))
    return _exit_code_for_result(result)


if __name__ == "__main__":
    sys.exit(main())


# Backwards-compatible export for tests
ACTIVE_STATIC_GATE = ACTIVE_STATIC_GATE_NAME
