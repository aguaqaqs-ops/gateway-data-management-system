"""WP0-R2 affected-scope router and P2-PR-STATIC gate tests."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import subprocess
import sys
from concurrent import futures
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest import mock

import pytest

from gate import (
    ACTIVE_STATIC_GATE,
    GateCommand,
    RevisionClosure,
    RoutingStatus,
    StaticCheck,
    StaticStatus,
    TRUNCATION_MARKER,
    _execute_static_checks,
    _static_checks_for_routing,
    gate_result_to_dict,
    parse_gate_command,
    routing_view_from_result,
    run_gate_command,
)
from router import (
    EXPECTED_GATE_ACTIVATION,
    EXPECTED_GATE_OWNERS,
    INVENTORY_SCHEMA_ID,
    INVENTORY_SCHEMA_VERSION,
    KNOWN_GATES,
    PathChange,
    RouterError,
    RouterErrorCode,
    RoutingResult,
    default_inventory_path,
    load_inventory,
    parse_inventory,
    route_changes,
    validate_inventory_rule_prefix,
    validate_repo_relative_path,
)

REPO_ROOT = Path(__file__).resolve().parents[4]
CONFORMANCE_ROOT = REPO_ROOT / "vnext" / "conformance"
GATE_SCRIPT = CONFORMANCE_ROOT / "phase2" / "gate.py"
PHASE1_CONTAINER_GATE = "PHASE-EXIT-CONTAINER"

ALL_GATES = (
    "P2-PR-CONTRACT",
    "P2-PHASE-EXIT-CONTAINER",
    "P2-PR-RECOVERY",
    "P2-PR-STATIC",
    "PR-CORRECTNESS",
    "PR-NATIVE",
)


@dataclass(frozen=True)
class PathCase:
    path: str
    status: str = "modified"
    old_path: str | None = None


def _inventory_raw() -> dict[str, Any]:
    inventory = load_inventory()
    return {
        "schema_id": inventory.schema_id,
        "schema_version": inventory.schema_version,
        "gates": {
            name: {
                "activation": activation,
                "owner": EXPECTED_GATE_OWNERS[name],
            }
            for name, activation in inventory.gates
        },
        "rules": [
            {
                "id": rule.rule_id,
                "paths": list(rule.paths),
                "gates": list(rule.gates),
                **({"narrow": True} if rule.narrow else {}),
            }
            for rule in inventory.rules
        ],
        "unknown_path_gates": list(inventory.unknown_path_gates),
        "empty_change_set_policy": inventory.empty_change_set_policy,
    }


def _route(paths: list[PathCase]) -> set[str]:
    changes = [
        PathChange(path=item.path, status=item.status, old_path=item.old_path)  # type: ignore[arg-type]
        for item in paths
    ]
    return set(route_changes(changes).selected_gates)


def _route_result(paths: list[PathCase]) -> RoutingResult:
    changes = [
        PathChange(path=item.path, status=item.status, old_path=item.old_path)  # type: ignore[arg-type]
        for item in paths
    ]
    return route_changes(changes)


def test_inventory_schema_version_positive() -> None:
    inventory = load_inventory()
    assert inventory.schema_id == INVENTORY_SCHEMA_ID
    assert inventory.schema_version == INVENTORY_SCHEMA_VERSION
    assert set(name for name, _ in inventory.gates) == set(KNOWN_GATES)
    assert set(inventory.unknown_path_gates) == set(KNOWN_GATES)
    for gate_name, activation in inventory.gates:
        assert activation == EXPECTED_GATE_ACTIVATION[gate_name]
    assert default_inventory_path().is_file()


@pytest.mark.parametrize(
    ("mutator", "expected_code"),
    [
        (lambda data: data | {"schema_id": "wrong"}, RouterErrorCode.SCHEMA_MISMATCH),
        (lambda data: data | {"schema_version": 99}, RouterErrorCode.SCHEMA_MISMATCH),
        (lambda data: data | {"unexpected": True}, RouterErrorCode.UNKNOWN_INVENTORY_FIELD),
        (
            lambda data: {
                **data,
                "gates": {
                    **data["gates"],
                    "MADE-UP-GATE": {
                        "activation": "inactive",
                        "owner": "phase2-conformance",
                    },
                },
            },
            RouterErrorCode.INVALID_INVENTORY,
        ),
        (
            lambda data: {
                **data,
                "gates": {
                    **data["gates"],
                    "P2-PR-CONTRACT": {
                        "activation": "active",
                        "owner": EXPECTED_GATE_OWNERS["P2-PR-CONTRACT"],
                    },
                },
            },
            RouterErrorCode.INVALID_INVENTORY,
        ),
        (
            lambda data: {
                **data,
                "unknown_path_gates": [
                    gate for gate in data["unknown_path_gates"] if gate != "PR-NATIVE"
                ],
            },
            RouterErrorCode.INVALID_INVENTORY,
        ),
        (
            lambda data: {
                **data,
                "rules": [
                    {
                        **data["rules"][0],
                        "paths": [123],
                    },
                    *data["rules"][1:],
                ],
            },
            RouterErrorCode.INVALID_INVENTORY,
        ),
        (
            lambda data: {
                **data,
                "rules": [
                    *data["rules"],
                    {
                        "id": "shadow-repository-src",
                        "paths": ["vnext/repository_service/src"],
                        "gates": ["P2-PR-STATIC"],
                    },
                ],
            },
            RouterErrorCode.CONFLICTING_RULE_PREFIX,
        ),
        (
            lambda data: {
                **data,
                "gates": {
                    **data["gates"],
                    "P2-PR-STATIC": {
                        "activation": "active",
                    },
                },
            },
            RouterErrorCode.INVALID_INVENTORY,
        ),
        (
            lambda data: {
                **data,
                "rules": [
                    {
                        **data["rules"][0],
                        "gates": [*data["rules"][0]["gates"], "P2-PR-UNKNOWN"],
                    },
                    *data["rules"][1:],
                ],
            },
            RouterErrorCode.UNKNOWN_GATE,
        ),
        (
            lambda data: {
                **data,
                "rules": data["rules"] + [data["rules"][0]],
            },
            RouterErrorCode.DUPLICATE_RULE_ID,
        ),
        (
            lambda data: {
                **data,
                "rules": [
                    *data["rules"],
                    {
                        "id": "shadow-dup-path",
                        "paths": [data["rules"][0]["paths"][0]],
                        "gates": ["P2-PR-STATIC"],
                    },
                ],
            },
            RouterErrorCode.DUPLICATE_RULE_PATH,
        ),
        (
            lambda data: {
                **data,
                "rules": [
                    {
                        **data["rules"][0],
                        "gates": ["P2-PR-STATIC", "P2-PR-STATIC"],
                    },
                    *data["rules"][1:],
                ],
            },
            RouterErrorCode.DUPLICATE_GATE,
        ),
        (
            lambda data: {
                **data,
                "rules": [
                    {
                        **data["rules"][0],
                        "narrow": "false",
                    },
                    *data["rules"][1:],
                ],
            },
            RouterErrorCode.INVALID_INVENTORY,
        ),
    ],
)
def test_inventory_negative(mutator: Any, expected_code: RouterErrorCode) -> None:
    mutated = mutator(_inventory_raw())
    with pytest.raises(RouterError) as exc:
        parse_inventory(mutated)
    assert exc.value.code is expected_code


def test_phase1_container_gate_not_in_taxonomy() -> None:
    inventory = load_inventory()
    gate_names = {name for name, _ in inventory.gates}
    assert PHASE1_CONTAINER_GATE not in gate_names
    assert PHASE1_CONTAINER_GATE not in inventory.unknown_path_gates


def test_known_phase2_source_path_selects_static_and_contract() -> None:
    gates = _route(
        [PathCase("vnext/repository_service/src/gateway_repository_service/__init__.py")]
    )
    assert {"P2-PR-STATIC", "P2-PR-CONTRACT"} <= gates


def test_formal_authority_expands_to_all_gates_without_phase1_container() -> None:
    gates = _route(
        [
            PathCase(
                "docs/backend-vnext/refactoring/formal/plans/phase-2-implementation-design-and-delivery-plan.md"
            )
        ]
    )
    assert set(ALL_GATES) <= gates
    assert PHASE1_CONTAINER_GATE not in gates


def test_repository_lock_and_pyproject_select_static_and_contract() -> None:
    for path in (
        "vnext/repository_contracts/uv.lock",
        "vnext/repository_contracts/pyproject.toml",
        "vnext/repository_client/uv.lock",
        "vnext/repository_client/pyproject.toml",
        "vnext/repository_service/uv.lock",
        "vnext/repository_service/pyproject.toml",
    ):
        gates = _route([PathCase(path)])
        assert gates == {"P2-PR-CONTRACT", "P2-PR-STATIC"}, path


def test_repository_source_paths_select_static_and_contract() -> None:
    for path in (
        "vnext/repository_contracts/src/gateway_repository_contracts/__init__.py",
        "vnext/repository_client/src/gateway_repository_client/__init__.py",
        "vnext/repository_service/src/gateway_repository_service/__init__.py",
    ):
        gates = _route([PathCase(path)])
        assert gates == {"P2-PR-CONTRACT", "P2-PR-STATIC"}, path


def test_workspace_inventory_selects_static() -> None:
    gates = _route([PathCase("vnext/repository-workspace.toml")])
    assert gates == {"P2-PR-STATIC"}


def test_shared_kernel_fixtures_and_conformance_core_select_correctness() -> None:
    assert "PR-CORRECTNESS" in _route(
        [PathCase("vnext/shared_kernel/src/gateway_shared_kernel/__init__.py")]
    )
    assert "PR-CORRECTNESS" in _route(
        [PathCase("vnext/fixtures/schemas/definitions-v1.schema.json")]
    )
    assert "PR-CORRECTNESS" in _route(
        [PathCase("vnext/conformance/src/gateway_conformance/errors.py")]
    )


def test_backend_rust_lock_build_selects_native_and_correctness() -> None:
    gates = _route([PathCase("vnext/rust/Cargo.lock")])
    assert {"P2-PR-STATIC", "PR-CORRECTNESS", "PR-NATIVE"} <= gates
    backend_gates = _route([PathCase("vnext/backend/src/gateway_backend/app.py")])
    assert {"PR-NATIVE", "PR-CORRECTNESS", "P2-PR-STATIC"} <= backend_gates


def test_deploy_path_selects_container_gate_inactive_in_inventory() -> None:
    result = _route_result([PathCase("vnext/deploy/compose.yaml")])
    assert "P2-PHASE-EXIT-CONTAINER" in result.selected_gates
    assert dict(result.gate_activation)["P2-PHASE-EXIT-CONTAINER"] == "inactive"
    assert PHASE1_CONTAINER_GATE not in result.selected_gates


def test_unknown_path_fail_closed_expands_all_gates_without_phase1_container() -> None:
    result = _route_result([PathCase("totally/unknown/path.txt")])
    assert set(result.selected_gates) == set(ALL_GATES)
    assert PHASE1_CONTAINER_GATE not in result.selected_gates
    assert result.fail_closed is True


def test_deleted_file_still_routes_without_filesystem_check() -> None:
    gates = _route(
        [PathCase("vnext/repository_client/src/gateway_repository_client/__init__.py", "deleted")]
    )
    assert {"P2-PR-STATIC", "P2-PR-CONTRACT"} <= gates


def test_rename_unions_old_and_new_path_gates() -> None:
    gates = _route(
        [
            PathCase(
                "vnext/repository_contracts/src/gateway_repository_contracts/__init__.py",
                "renamed",
                "vnext/conformance/src/gateway_conformance/errors.py",
            )
        ]
    )
    assert {"P2-PR-STATIC", "P2-PR-CONTRACT", "PR-CORRECTNESS"} <= gates


def test_copied_unions_old_and_new_path_gates() -> None:
    gates = _route(
        [
            PathCase(
                "vnext/repository_client/src/gateway_repository_client/__init__.py",
                "copied",
                "vnext/repository_contracts/src/gateway_repository_contracts/__init__.py",
            )
        ]
    )
    assert {"P2-PR-STATIC", "P2-PR-CONTRACT"} <= gates


@pytest.mark.parametrize(
    "change",
    [
        PathChange(path="vnext/a.py", status="renamed"),
        PathChange(path="vnext/a.py", status="renamed", old_path="vnext/a.py"),
        PathChange(path="vnext/a.py", status="modified", old_path="vnext/b.py"),
        PathChange(path="vnext/a.py", status="copied"),
    ],
)
def test_malformed_rename_or_copy(change: PathChange) -> None:
    with pytest.raises(RouterError) as exc:
        route_changes([change])
    assert exc.value.code in {
        RouterErrorCode.MALFORMED_RENAME,
        RouterErrorCode.MALFORMED_COPY,
    }


def test_duplicate_changes_and_input_reordering_are_deterministic() -> None:
    first = [
        PathChange(path="vnext/repository_client/foo.py", status="modified"),
        PathChange(path="vnext/repository_client/foo.py", status="modified"),
        PathChange(path="vnext/shared_kernel/bar.py", status="added"),
    ]
    second = list(reversed(first))
    assert route_changes(first) == route_changes(second)


@pytest.mark.parametrize(
    ("path", "expected_code"),
    [
        ("/absolute/path", RouterErrorCode.ABSOLUTE_PATH),
        ("C:/absolute/path", RouterErrorCode.ABSOLUTE_PATH),
        ("c:/absolute/path", RouterErrorCode.ABSOLUTE_PATH),
        ("vnext/../secret", RouterErrorCode.PARENT_TRAVERSAL),
        ("", RouterErrorCode.EMPTY_PATH),
        ("vnext\\secret", RouterErrorCode.UNSUPPORTED_SEPARATOR),
        ("vnext//double", RouterErrorCode.NONCANONICAL_PATH),
        ("./vnext/repository_client/a.py", RouterErrorCode.NONCANONICAL_PATH),
        ("vnext/repository_client/a.py/", RouterErrorCode.NONCANONICAL_PATH),
        ("vnext/./repository_client/a.py", RouterErrorCode.NONCANONICAL_PATH),
        ("vnext/repository_client/a.py/.", RouterErrorCode.NONCANONICAL_PATH),
        ("vnext/repository\x00client/a.py", RouterErrorCode.NONCANONICAL_PATH),
    ],
)
def test_invalid_paths_rejected(path: str, expected_code: RouterErrorCode) -> None:
    with pytest.raises(RouterError) as exc:
        route_changes([PathChange(path=path, status="modified")])
    assert exc.value.code is expected_code


def test_canonical_path_must_match_exactly() -> None:
    assert (
        validate_repo_relative_path("vnext/repository_client/a.py")
        == "vnext/repository_client/a.py"
    )
    with pytest.raises(RouterError) as exc:
        validate_repo_relative_path("./vnext/repository_client/a.py")
    assert exc.value.code is RouterErrorCode.NONCANONICAL_PATH


def test_unknown_change_status_rejected() -> None:
    with pytest.raises(RouterError) as exc:
        route_changes([PathChange(path="vnext/repository_client/a.py", status="mystery")])  # type: ignore[arg-type]
    assert exc.value.code is RouterErrorCode.UNKNOWN_CHANGE_STATUS


def test_empty_change_set_does_not_pass_execute() -> None:
    result = run_gate_command(
        parse_gate_command(
            {
                "schema_version": 1,
                "command": "execute",
                "changes": [],
                "repo_root": str(REPO_ROOT),
            }
        )
    )
    assert result.static_status is StaticStatus.FAIL
    assert RouterErrorCode.EMPTY_CHANGE_SET.value in result.diagnostics


def test_route_unknown_path_uses_routing_status_not_aggregate_pass() -> None:
    result = run_gate_command(
        parse_gate_command(
            {
                "schema_version": 1,
                "command": "route",
                "changes": [{"path": "unknown/file.txt", "status": "modified"}],
                "repo_root": str(REPO_ROOT),
            }
        )
    )
    assert result.routing_status is RoutingStatus.ROUTED
    assert result.static_status is None
    assert "aggregate_status" not in gate_result_to_dict(result)
    assert result.pending_external_gates
    for outcome in result.gate_outcomes:
        if outcome.activation in {"inactive", "external"}:
            assert outcome.status != "PASS"


def test_execute_phase2_only_complete_closure_with_static_pass() -> None:
    result = run_gate_command(
        parse_gate_command(
            {
                "schema_version": 1,
                "command": "execute",
                "changes": [{"path": "vnext/conformance/phase2/router.py", "status": "modified"}],
                "repo_root": str(REPO_ROOT),
                "static_checks": ["injected_failure"],
            }
        )
    )
    assert result.static_status is StaticStatus.FAIL
    assert result.revision_closure is RevisionClosure.INCOMPLETE


def test_execute_full_candidate_static_independent_with_incomplete_closure() -> None:
    result = run_gate_command(
        parse_gate_command(
            {
                "schema_version": 1,
                "command": "execute",
                "changes": [
                    {"path": "vnext/conformance/phase2/router.py", "status": "modified"},
                    {
                        "path": "vnext/shared_kernel/src/gateway_shared_kernel/__init__.py",
                        "status": "modified",
                    },
                ],
                "repo_root": str(REPO_ROOT),
                "static_checks": ["injected_failure"],
            }
        )
    )
    assert {"PR-CORRECTNESS"} <= set(result.pending_external_gates)
    assert result.revision_closure is RevisionClosure.INCOMPLETE
    static = [item for item in result.gate_outcomes if item.gate == ACTIVE_STATIC_GATE]
    assert static
    assert static[0].status == "FAIL"


def test_inactive_gates_never_receive_pass() -> None:
    result = run_gate_command(
        parse_gate_command(
            {
                "schema_version": 1,
                "command": "route",
                "changes": [{"path": "vnext/deploy/compose.yaml", "status": "modified"}],
                "repo_root": str(REPO_ROOT),
            }
        )
    )
    for outcome in result.gate_outcomes:
        if outcome.activation in {"inactive", "external"}:
            assert outcome.status != "PASS"


def test_active_static_failure_propagates_fail() -> None:
    result = run_gate_command(
        parse_gate_command(
            {
                "schema_version": 1,
                "command": "execute",
                "changes": [{"path": "vnext/conformance/phase2/router.py", "status": "modified"}],
                "repo_root": str(REPO_ROOT),
                "static_checks": ["injected_failure"],
            }
        )
    )
    static = [item for item in result.gate_outcomes if item.gate == ACTIVE_STATIC_GATE]
    assert static
    assert static[0].status == "FAIL"
    assert result.static_status is StaticStatus.FAIL


def test_unknown_command_field_rejected() -> None:
    with pytest.raises(RouterError) as exc:
        parse_gate_command(
            {
                "schema_version": 1,
                "command": "route",
                "changes": [],
                "repo_root": str(REPO_ROOT),
                "unexpected": True,
            }
        )
    assert exc.value.code is RouterErrorCode.UNKNOWN_FIELD


def test_unknown_change_field_rejected() -> None:
    with pytest.raises(RouterError) as exc:
        parse_gate_command(
            {
                "schema_version": 1,
                "command": "route",
                "changes": [{"path": "vnext/a.py", "status": "modified", "extra": True}],
                "repo_root": str(REPO_ROOT),
            }
        )
    assert exc.value.code is RouterErrorCode.UNKNOWN_FIELD


def test_frozen_routing_result_rejects_mutation() -> None:
    result = _route_result([PathCase("unknown/file.txt")])
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.selected_gates = ()  # type: ignore[misc]


def test_gate_execute_does_not_mutate_tracked_worktree() -> None:
    lock_paths = [
        REPO_ROOT / "vnext/conformance/uv.lock",
        REPO_ROOT / "vnext/repository_service/uv.lock",
    ]
    before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in lock_paths}
    result = run_gate_command(
        parse_gate_command(
            {
                "schema_version": 1,
                "command": "execute",
                "changes": [{"path": "vnext/conformance/phase2/router.py", "status": "modified"}],
                "repo_root": str(REPO_ROOT),
                "static_checks": ["injected_failure"],
            }
        )
    )
    after = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in lock_paths}
    assert before == after
    assert "tracked_worktree_mutated" not in result.diagnostics


def test_worktree_snapshot_detects_index_mode_change(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    tracked = repo / "a.txt"
    tracked.write_text("hello\n", encoding="utf-8")
    subprocess.run(["git", "add", "a.txt"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init", "--author", "test <test@test>"],
        cwd=repo,
        check=True,
        capture_output=True,
        env={
            **os.environ,
            "GIT_AUTHOR_DATE": "2026-01-01T00:00:00",
            "GIT_COMMITTER_DATE": "2026-01-01T00:00:00",
        },
    )
    from gate import _tracked_worktree_snapshot, _worktree_unchanged

    before, error = _tracked_worktree_snapshot(repo)
    assert error is None
    subprocess.run(
        ["git", "update-index", "--chmod=+x", "a.txt"], cwd=repo, check=True, capture_output=True
    )
    unchanged, mode_error = _worktree_unchanged(repo, before)
    assert mode_error is None
    assert unchanged is False


def test_worktree_snapshot_fails_for_non_git_path(tmp_path: Path) -> None:
    from gate import _tracked_worktree_snapshot

    snapshot, error = _tracked_worktree_snapshot(tmp_path)
    assert snapshot == ()
    assert error == "worktree_snapshot_failed"


def test_diagnostics_use_stable_check_ids_without_host_paths() -> None:
    result = run_gate_command(
        parse_gate_command(
            {
                "schema_version": 1,
                "command": "execute",
                "changes": [{"path": "vnext/conformance/phase2/router.py", "status": "modified"}],
                "repo_root": str(REPO_ROOT),
                "static_checks": ["injected_failure"],
            }
        )
    )
    assert any(item.startswith("check:static.injected:") for item in result.diagnostics)
    joined = "\n".join(result.diagnostics)
    assert "/tmp/" not in joined
    assert str(REPO_ROOT) not in joined


def test_signal_failure_maps_to_fail_not_blocked() -> None:
    from gate import StaticCheck, _execute_static_checks

    with mock.patch("gate._run_subprocess") as run_subprocess:
        run_subprocess.return_value = subprocess.CompletedProcess(
            args=("python",),
            returncode=-9,
            stdout="",
            stderr="killed",
        )
        status, diagnostics = _execute_static_checks(
            [StaticCheck("static.test", Path("."), ("python", "-c", "import sys; sys.exit(0)"))],
            extra_checks=(),
        )
    assert status is StaticStatus.FAIL
    assert any("check:static.test:exit=-9" in item for item in diagnostics)


def test_gate_route_smoke_representative_paths() -> None:
    cases = [
        [{"path": "unknown/file.txt", "status": "modified"}],
        [
            {
                "path": "vnext/repository_client/src/x.py",
                "status": "renamed",
                "old_path": "vnext/repository_client/src/y.py",
            }
        ],
        [{"path": "vnext/repository_contracts/uv.lock", "status": "modified"}],
        [
            {
                "path": "docs/backend-vnext/refactoring/formal/README.md",
                "status": "modified",
            }
        ],
        [{"path": "vnext/deploy/compose.yaml", "status": "deleted"}],
    ]
    for changes in cases:
        result = run_gate_command(
            parse_gate_command(
                {
                    "schema_version": 1,
                    "command": "route",
                    "changes": changes,
                    "repo_root": str(REPO_ROOT),
                }
            )
        )
        assert result.routing_status is RoutingStatus.ROUTED
        assert result.routing.selected_gates
        assert PHASE1_CONTAINER_GATE not in result.routing.selected_gates


def test_gate_result_is_immutable_json_shape() -> None:
    command = parse_gate_command(
        {
            "schema_version": 1,
            "command": "route",
            "changes": [{"path": "vnext/conformance/phase2/gate.py", "status": "modified"}],
            "repo_root": str(REPO_ROOT),
        }
    )
    result = run_gate_command(command)
    payload = gate_result_to_dict(result)
    assert payload["schema_version"] == 1
    assert payload["routing_status"] == "ROUTED"
    assert "routing" in payload
    assert "gate_outcomes" in payload
    assert "aggregate_status" not in payload


def test_worktree_snapshot_detects_modified_content_change(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    tracked = repo / "a.txt"
    tracked.write_text("hello\n", encoding="utf-8")
    subprocess.run(["git", "add", "a.txt"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init", "--author", "test <test@test>"],
        cwd=repo,
        check=True,
        capture_output=True,
        env={
            **os.environ,
            "GIT_AUTHOR_DATE": "2026-01-01T00:00:00",
            "GIT_COMMITTER_DATE": "2026-01-01T00:00:00",
        },
    )
    tracked.write_text("changed once\n", encoding="utf-8")
    from gate import _tracked_worktree_snapshot, _worktree_unchanged

    before, error = _tracked_worktree_snapshot(repo)
    assert error is None
    tracked.write_text("changed twice\n", encoding="utf-8")
    unchanged, content_error = _worktree_unchanged(repo, before)
    assert content_error is None
    assert unchanged is False


def _init_git_repo(repo: Path) -> None:
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test"], cwd=repo, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.name", "test"], cwd=repo, check=True, capture_output=True
    )


def _commit_all(repo: Path, message: str = "init") -> None:
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", message, "--author", "test <test@test>"],
        cwd=repo,
        check=True,
        capture_output=True,
        env={
            **os.environ,
            "GIT_AUTHOR_DATE": "2026-01-01T00:00:00",
            "GIT_COMMITTER_DATE": "2026-01-01T00:00:00",
        },
    )


@pytest.mark.parametrize(
    "invalid_root",
    [None, 1, True, [{"id": "x"}]],
)
def test_parse_inventory_rejects_non_mapping_root(invalid_root: object) -> None:
    with pytest.raises(RouterError) as exc:
        parse_inventory(invalid_root)
    assert exc.value.code is RouterErrorCode.INVALID_INVENTORY


@pytest.mark.parametrize(
    "prefix",
    ["./vnext/backend", "vnext/./backend", "vnext/backend/.", "./vnext/backend/"],
)
def test_inventory_rule_prefix_rejects_noncanonical(prefix: str) -> None:
    with pytest.raises(RouterError) as exc:
        validate_inventory_rule_prefix(prefix)
    assert exc.value.code is RouterErrorCode.NONCANONICAL_PATH


def test_inventory_rule_prefix_accepts_trailing_slash_directory() -> None:
    assert validate_inventory_rule_prefix("vnext/backend/") == "vnext/backend/"


def test_inventory_rule_prefix_rejects_integer_path_in_rules() -> None:
    mutated = _inventory_raw()
    mutated["rules"] = [
        {
            **mutated["rules"][0],
            "paths": [123],
        },
        *mutated["rules"][1:],
    ]
    with pytest.raises(RouterError) as exc:
        parse_inventory(mutated)
    assert exc.value.code is RouterErrorCode.INVALID_INVENTORY


def test_bounded_capture_records_stdout_and_stderr_tails() -> None:
    from gate import StaticCheck, _execute_static_checks

    long_stdout = "A" * 5000 + "stdout-marker"
    long_stderr = "B" * 5000 + "stderr-marker"
    with mock.patch("gate._run_subprocess") as run_subprocess:
        run_subprocess.return_value = subprocess.CompletedProcess(
            args=("python",),
            returncode=1,
            stdout=long_stdout,
            stderr=long_stderr,
        )
        status, diagnostics = _execute_static_checks(
            [StaticCheck("static.test", Path("."), ("python", "-c", "raise SystemExit(1)"))],
            extra_checks=(),
        )
    assert status is StaticStatus.FAIL
    joined = "\n".join(diagnostics)
    assert "stdout-marker" in joined
    assert "stderr-marker" in joined
    assert TRUNCATION_MARKER in joined


_INVALID_UTF8_SCRIPT = """
import sys

order = sys.argv[1]
size = 1024 * 1024
stdout_marker = b"stdout-marker"
stderr_marker = b"stderr-marker"
if order == "invalid_utf8_stderr":
    sys.stderr.buffer.write(b"\\xff" * size)
    sys.stderr.buffer.write(stderr_marker)
    sys.stderr.buffer.flush()
    sys.stdout.buffer.write(stdout_marker)
elif order == "invalid_utf8_stdout":
    sys.stdout.buffer.write(b"\\xff" * size)
    sys.stdout.buffer.write(stdout_marker)
    sys.stdout.buffer.flush()
    sys.stderr.buffer.write(stderr_marker)
else:
    sys.stdout.buffer.write(b"\\xff" * size)
    sys.stdout.buffer.write(stdout_marker)
    sys.stderr.buffer.write(b"\\xff" * size)
    sys.stderr.buffer.write(stderr_marker)
raise SystemExit(1)
"""


@pytest.mark.parametrize(
    "order",
    ["invalid_utf8_stderr", "invalid_utf8_stdout", "invalid_utf8_both"],
)
def test_subprocess_capture_handles_invalid_utf8_without_deadlock(order: str) -> None:
    from gate import StaticCheck, _execute_static_checks

    argv = (sys.executable, "-c", _INVALID_UTF8_SCRIPT, order)

    def run_checks() -> tuple[object, tuple[str, ...]]:
        return _execute_static_checks(
            [StaticCheck("static.pipe", Path("."), argv)],
            extra_checks=(),
        )

    with futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(run_checks)
        status, diagnostics = future.result(timeout=5)

    assert status is StaticStatus.FAIL
    joined = "\n".join(diagnostics)
    assert "check:static.pipe:exit=1" in joined
    assert "stdout-marker" in joined or "stderr-marker" in joined


_HIGH_OUTPUT_SCRIPT = """
import sys

order = sys.argv[1]
size = 1024 * 1024
if order == "stderr_first":
    sys.stderr.write("E" * size)
    sys.stderr.write("stderr-marker")
    sys.stderr.flush()
    sys.stdout.write("stdout-marker")
elif order == "stdout_first":
    sys.stdout.write("O" * size)
    sys.stdout.write("stdout-marker")
    sys.stdout.flush()
    sys.stderr.write("stderr-marker")
else:
    sys.stdout.write("O" * size)
    sys.stdout.write("stdout-marker")
    sys.stderr.write("E" * size)
    sys.stderr.write("stderr-marker")
raise SystemExit(1)
"""


@pytest.mark.parametrize("order", ["stderr_first", "stdout_first", "both_large"])
def test_subprocess_capture_drains_both_pipes_without_deadlock(order: str) -> None:
    from gate import StaticCheck, _execute_static_checks

    argv = (sys.executable, "-c", _HIGH_OUTPUT_SCRIPT, order)

    def run_checks() -> tuple[object, tuple[str, ...]]:
        return _execute_static_checks(
            [StaticCheck("static.pipe", Path("."), argv)],
            extra_checks=(),
        )

    with futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(run_checks)
        status, diagnostics = future.result(timeout=5)

    assert status is StaticStatus.FAIL
    joined = "\n".join(diagnostics)
    assert "stdout-marker" in joined
    assert "stderr-marker" in joined
    assert TRUNCATION_MARKER in joined


def test_worktree_snapshot_succeeds_with_tracked_deletion(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)
    tracked = repo / ".gitignore"
    tracked.write_text("*.pyc\n", encoding="utf-8")
    _commit_all(repo)
    tracked.unlink()
    from gate import _tracked_worktree_snapshot

    snapshot, error = _tracked_worktree_snapshot(repo)
    assert error is None
    assert any(item == "content:.gitignore:deleted" for item in snapshot)


def test_worktree_snapshot_succeeds_with_unstaged_rename(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)
    tracked = repo / "a.txt"
    tracked.write_text("hello\n", encoding="utf-8")
    _commit_all(repo)
    (repo / "b.txt").write_text("hello\n", encoding="utf-8")
    tracked.unlink()
    from gate import _tracked_worktree_snapshot

    snapshot, error = _tracked_worktree_snapshot(repo)
    assert error is None
    assert any(item == "content:a.txt:deleted" for item in snapshot)


def test_worktree_snapshot_detects_delete_during_execute(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)
    tracked = repo / "a.txt"
    tracked.write_text("hello\n", encoding="utf-8")
    _commit_all(repo)
    from gate import _tracked_worktree_snapshot, _worktree_unchanged

    before, error = _tracked_worktree_snapshot(repo)
    assert error is None
    tracked.unlink()
    unchanged, mutation_error = _worktree_unchanged(repo, before)
    assert mutation_error is None
    assert unchanged is False


def test_worktree_snapshot_handles_special_filename(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)
    tracked = repo / "space name.txt"
    tracked.write_text("hello\n", encoding="utf-8")
    _commit_all(repo)
    from gate import _tracked_worktree_snapshot

    snapshot, error = _tracked_worktree_snapshot(repo)
    assert error is None
    assert any(item.startswith("content:space name.txt:") for item in snapshot)


def test_worktree_snapshot_detects_dangling_symlink_target_change(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)
    link = repo / "link"
    link.symlink_to("missing-one")
    subprocess.run(["git", "add", "link"], cwd=repo, check=True, capture_output=True)
    _commit_all(repo)
    link.unlink()
    link.symlink_to("missing-two")
    from gate import _tracked_worktree_snapshot, _worktree_unchanged

    before, error = _tracked_worktree_snapshot(repo)
    assert error is None
    assert any(item.startswith("content:link:symlink:") for item in before)
    link.unlink()
    link.symlink_to("missing-three")
    unchanged, mutation_error = _worktree_unchanged(repo, before)
    assert mutation_error is None
    assert unchanged is False


def test_load_inventory_rejects_invalid_utf8_bytes(tmp_path: Path) -> None:
    from gateway_conformance.strict_yaml import StrictYAMLValidationError

    bad = tmp_path / "bad.yaml"
    bad.write_bytes(b"\xff\xfe")
    with pytest.raises(StrictYAMLValidationError):
        load_inventory(bad)


def test_cli_rejects_invalid_utf8_inventory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import gate as gate_module
    import router as router_module

    bad = tmp_path / "bad.yaml"
    bad.write_bytes(b"\xff\xfe")
    monkeypatch.setattr(router_module, "default_inventory_path", lambda: bad)
    exit_code = gate_module.main(
        [
            "route",
            "--changes-json",
            json.dumps([{"path": "vnext/conformance/phase2/router.py", "status": "modified"}]),
            "--repo-root",
            str(REPO_ROOT),
        ]
    )
    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.err == "" or "Traceback" not in captured.err
    assert json.loads(captured.out) == {"error": RouterErrorCode.INVALID_INVENTORY.value}


def test_execute_with_tracked_deletion_is_not_blocked_by_snapshot(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)
    tracked = repo / ".gitignore"
    tracked.write_text("*.pyc\n", encoding="utf-8")
    _commit_all(repo)
    tracked.unlink()
    result = run_gate_command(
        parse_gate_command(
            {
                "schema_version": 1,
                "command": "execute",
                "changes": [{"path": "vnext/conformance/phase2/router.py", "status": "modified"}],
                "repo_root": str(repo),
                "static_checks": ["injected_failure"],
            }
        )
    )
    assert result.static_status is StaticStatus.FAIL
    assert "worktree_snapshot_failed" not in result.diagnostics


def _run_gate_cli(
    *args: str,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(GATE_SCRIPT), *args],
        cwd=CONFORMANCE_ROOT,
        env={**os.environ, **(env or {})},
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.nested_cli
def test_cli_route_positive_emits_json_and_exit_zero() -> None:
    proc = _run_gate_cli(
        "route",
        "--changes-json",
        json.dumps([{"path": "vnext/conformance/phase2/router.py", "status": "modified"}]),
        "--repo-root",
        str(REPO_ROOT),
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["routing_status"] == "ROUTED"
    assert "P2-PR-STATIC" in payload["routing"]["selected_gates"]


@pytest.mark.nested_cli
def test_cli_route_unknown_path_expands_all_gates() -> None:
    proc = _run_gate_cli(
        "route",
        "--changes-json",
        json.dumps([{"path": "unknown/x", "status": "modified"}]),
        "--repo-root",
        str(REPO_ROOT),
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert set(payload["routing"]["selected_gates"]) == set(ALL_GATES)


@pytest.mark.nested_cli
def test_cli_route_malformed_json_exits_nonzero() -> None:
    proc = _run_gate_cli(
        "route",
        "--changes-json",
        "{not-json",
        "--repo-root",
        str(REPO_ROOT),
    )
    assert proc.returncode == 1
    assert "invalid_json" in proc.stdout


@pytest.mark.nested_cli
def test_cli_execute_empty_changes_exits_nonzero() -> None:
    proc = _run_gate_cli(
        "execute",
        "--changes-json",
        "[]",
        "--repo-root",
        str(REPO_ROOT),
    )
    assert proc.returncode == 1
    payload = json.loads(proc.stdout)
    assert payload["static_status"] == "FAIL"


@pytest.mark.nested_cli
def test_cli_execute_blocked_on_non_git_repo(tmp_path: Path) -> None:
    proc = _run_gate_cli(
        "execute",
        "--changes-json",
        json.dumps(
            [
                {
                    "path": "vnext/conformance/phase2/router.py",
                    "status": "modified",
                }
            ]
        ),
        "--repo-root",
        str(tmp_path),
    )
    assert proc.returncode == 3
    payload = json.loads(proc.stdout)
    assert payload["static_status"] == "BLOCKED"
    assert "worktree_snapshot_failed" in payload["diagnostics"]


@pytest.mark.nested_cli
def test_cli_execute_static_pass_without_injected_checks() -> None:
    proc = _run_gate_cli(
        "execute",
        "--changes-json",
        json.dumps(
            [
                {
                    "path": "vnext/conformance/phase2/router.py",
                    "status": "modified",
                }
            ]
        ),
        "--repo-root",
        str(REPO_ROOT),
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["static_status"] == "PASS"
    static_outcomes = [
        item for item in payload["gate_outcomes"] if item["gate"] == ACTIVE_STATIC_GATE
    ]
    assert static_outcomes
    assert static_outcomes[0]["status"] == "PASS"


def test_nested_cli_marker_is_registered() -> None:
    from _pytest.mark.structures import MarkDecorator

    assert isinstance(pytest.mark.nested_cli, MarkDecorator)


def test_static_checks_include_closure_lint() -> None:
    routing = routing_view_from_result(
        route_changes([PathChange("vnext/conformance/phase2/closure.py", "modified")])
    )
    checks = _static_checks_for_routing(
        routing, REPO_ROOT, ("vnext/conformance/phase2/closure.py",)
    )
    check_ids = [check.check_id for check in checks]
    assert "static.closure" in check_ids


def test_static_pytest_target_covers_phase2_tests_not_nested_cli() -> None:
    routing = routing_view_from_result(
        route_changes([PathChange("vnext/conformance/phase2/closure.py", "modified")])
    )
    checks = _static_checks_for_routing(
        routing, REPO_ROOT, ("vnext/conformance/phase2/closure.py",)
    )
    pytest_check = next(check for check in checks if check.check_id == "static.pytest")
    assert "phase2/tests" in pytest_check.argv
    assert "not nested_cli" in pytest_check.argv
    assert "test_router.py" not in pytest_check.argv


def test_static_checks_include_repository_contracts_on_hit() -> None:
    routing = routing_view_from_result(
        route_changes(
            [
                PathChange(
                    "vnext/repository_contracts/src/gateway_repository_contracts/stream.py",
                    "modified",
                )
            ]
        )
    )
    checks = _static_checks_for_routing(
        routing,
        REPO_ROOT,
        ("vnext/repository_contracts/src/gateway_repository_contracts/stream.py",),
    )
    check_ids = {check.check_id for check in checks}
    assert {
        "static.ruff.repository.contracts",
        "static.mypy.repository.contracts",
        "static.pytest.repository.contracts",
    } <= check_ids


def test_static_checks_exclude_repository_contracts_without_hit() -> None:
    routing = routing_view_from_result(
        route_changes([PathChange("vnext/conformance/phase2/closure.py", "modified")])
    )
    checks = _static_checks_for_routing(
        routing, REPO_ROOT, ("vnext/conformance/phase2/closure.py",)
    )
    check_ids = {check.check_id for check in checks}
    assert "static.ruff.repository.contracts" not in check_ids
    assert "static.mypy.repository.contracts" not in check_ids
    assert "static.pytest.repository.contracts" not in check_ids


def test_closure_lint_failure_propagates_as_static_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fail_closure(
        checks: list[StaticCheck], *, extra_checks: tuple[str, ...]
    ) -> tuple[StaticStatus, tuple[str, ...]]:
        diagnostics = [f"check:{check.check_id}:exit=1" for check in checks]
        return StaticStatus.FAIL, tuple(sorted(diagnostics))

    monkeypatch.setattr("gate._execute_static_checks", _fail_closure)
    result = run_gate_command(
        GateCommand(
            schema_version=1,
            command="execute",
            changes=(PathChange("vnext/conformance/phase2/closure.py", "modified"),),
            repo_root=REPO_ROOT,
        )
    )
    assert result.static_status is StaticStatus.FAIL
    assert any("static.closure" in item for item in result.diagnostics)


@pytest.mark.nested_cli
def test_closure_only_failure_via_real_gate_execute(tmp_path: Path) -> None:
    from test_closure import _clone_repo_fixture

    repo = _clone_repo_fixture(tmp_path)
    pins = repo / "vnext/deploy/phase-1-image-pins.env"
    pins.write_text(pins.read_text(encoding="utf-8") + "\n# mutated\n", encoding="utf-8")
    result = run_gate_command(
        GateCommand(
            schema_version=1,
            command="execute",
            changes=(PathChange("vnext/conformance/phase2/closure.py", "modified"),),
            repo_root=repo,
        )
    )
    assert result.static_status is StaticStatus.FAIL
    assert "check:static.closure:exit=1" in result.diagnostics
    assert "check:static.ruff:exit=0" in result.diagnostics
    assert "check:static.mypy:exit=0" in result.diagnostics
    assert "check:static.pytest:exit=0" in result.diagnostics
    closure_details = [
        item for item in result.diagnostics if item.startswith("detail:static.closure:")
    ]
    assert closure_details
    assert any("phase1.protection" in item for item in closure_details)
    closure_script = repo / "vnext/conformance/phase2/closure.py"
    proc = subprocess.run(
        [
            sys.executable,
            str(closure_script),
            "validate",
            "--repo-root",
            str(repo),
        ],
        cwd=repo / "vnext/conformance",
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 1
    payload = json.loads(proc.stdout)
    assert payload["ok"] is False
    assert any("phase1.protection" in item for item in payload["diagnostics"])


def test_closure_subprocess_pythonpath_isolated(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, str] = {}
    cwd = CONFORMANCE_ROOT

    def _capture_run(
        argv: tuple[str, ...], *, cwd: Path, env: dict[str, str]
    ) -> subprocess.CompletedProcess[str]:
        captured.update(env)
        return subprocess.CompletedProcess(list(argv), 0, "", "")

    monkeypatch.setattr("gate._run_subprocess", _capture_run)
    monkeypatch.setenv("PYTHONPATH", "/should/not/inherit")

    checks = [
        StaticCheck(
            "static.closure",
            cwd,
            (
                sys.executable,
                str(cwd / "phase2" / "closure.py"),
                "validate",
                "--repo-root",
                str(REPO_ROOT),
            ),
        )
    ]
    _execute_static_checks(checks, extra_checks=())

    expected = os.pathsep.join([str(cwd / "src"), str(cwd / "phase2")])
    assert captured["PYTHONPATH"] == expected
    assert "" not in captured["PYTHONPATH"].split(os.pathsep)
    assert "/should/not/inherit" not in captured["PYTHONPATH"]


def test_phase1_protection_failure_propagates_via_closure_check(tmp_path: Path) -> None:
    from test_closure import _clone_repo_fixture

    repo = _clone_repo_fixture(tmp_path)
    pins = repo / "vnext/deploy/phase-1-image-pins.env"
    pins.write_text(pins.read_text(encoding="utf-8") + "\n# mutated\n", encoding="utf-8")
    closure_script = CONFORMANCE_ROOT / "phase2" / "closure.py"
    proc = subprocess.run(
        [
            sys.executable,
            str(closure_script),
            "validate",
            "--repo-root",
            str(repo),
        ],
        cwd=CONFORMANCE_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 1
    payload = json.loads(proc.stdout)
    assert payload["ok"] is False
    assert any("phase1.protection" in item for item in payload["diagnostics"])


def test_execute_gate_worktree_unchanged_with_closure_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _pass_fast(
        checks: list[StaticCheck], *, extra_checks: tuple[str, ...]
    ) -> tuple[StaticStatus, tuple[str, ...]]:
        return StaticStatus.PASS, tuple(f"check:{check.check_id}:exit=0" for check in checks)

    monkeypatch.setattr("gate._execute_static_checks", _pass_fast)
    result = run_gate_command(
        GateCommand(
            schema_version=1,
            command="execute",
            changes=(PathChange("vnext/conformance/phase2/closure.py", "modified"),),
            repo_root=REPO_ROOT,
        )
    )
    assert result.static_status is StaticStatus.PASS
    assert "tracked_worktree_mutated" not in result.diagnostics
    assert any("static.closure" in item for item in result.diagnostics)
