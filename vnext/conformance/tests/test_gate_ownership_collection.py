"""Collection regression tests for gate authority ownership boundaries."""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path

from gate_ownership import (
    CONTAINER_MARKER_EXPR,
    CONTAINER_OWNED_BACKEND_MODULE,
    CONTAINER_OWNED_MODULES,
    CORRECTNESS_MARKER_EXPR,
    EXPECTED_CONTAINER_OWNED_COUNT,
)

CONFORMANCE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = CONFORMANCE_ROOT.parents[1]
BACKEND_ROOT = REPO_ROOT / "vnext" / "backend"
PYPROJECT = CONFORMANCE_ROOT / "pyproject.toml"
BACKEND_PYPROJECT = BACKEND_ROOT / "pyproject.toml"


def _collect_pytest(*, cwd: Path, marker: str) -> list[str]:
    proc = subprocess.run(
        [
            "uv",
            "run",
            "pytest",
            "--collect-only",
            "-q",
            "-m",
            marker,
        ],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=True,
    )
    collected: list[str] = []
    for line in proc.stdout.splitlines():
        stripped = line.strip()
        if stripped and "::" in stripped and not stripped.startswith("="):
            collected.append(stripped.split()[0])
    return collected


def test_phase_exit_container_marker_is_registered() -> None:
    conformance_text = PYPROJECT.read_text(encoding="utf-8")
    backend_text = BACKEND_PYPROJECT.read_text(encoding="utf-8")
    assert "phase_exit_container:" in conformance_text
    assert "phase_exit_container:" in backend_text


def test_correctness_collection_excludes_container_owned_tests() -> None:
    collected = _collect_pytest(cwd=CONFORMANCE_ROOT, marker=CORRECTNESS_MARKER_EXPR)
    for module in CONTAINER_OWNED_MODULES:
        assert not any(module in nodeid for nodeid in collected), module


def test_container_gate_collection_includes_all_owned_tests() -> None:
    conformance_collected = _collect_pytest(cwd=CONFORMANCE_ROOT, marker=CONTAINER_MARKER_EXPR)
    for module in CONTAINER_OWNED_MODULES:
        module_hits = [nodeid for nodeid in conformance_collected if module in nodeid]
        assert module_hits, module

    backend_collected = _collect_pytest(cwd=BACKEND_ROOT, marker=CONTAINER_MARKER_EXPR)
    backend_hits = [
        nodeid for nodeid in backend_collected if CONTAINER_OWNED_BACKEND_MODULE in nodeid
    ]
    assert backend_hits

    total = len(conformance_collected) + len(backend_collected)
    assert total == EXPECTED_CONTAINER_OWNED_COUNT


def test_container_owned_modules_have_module_level_marker() -> None:
    for relative in (*CONTAINER_OWNED_MODULES,):
        path = CONFORMANCE_ROOT / relative
        tree = ast.parse(path.read_text(encoding="utf-8"))
        has_marker = False
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "pytestmark":
                        has_marker = True
        assert has_marker, relative

    backend_path = BACKEND_ROOT / CONTAINER_OWNED_BACKEND_MODULE
    tree = ast.parse(backend_path.read_text(encoding="utf-8"))
    has_marker = any(
        isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "pytestmark" for target in node.targets
        )
        for node in tree.body
    )
    assert has_marker, CONTAINER_OWNED_BACKEND_MODULE


def test_frozen_phase_exit_gate_script_does_not_invoke_owned_pytest() -> None:
    text = (REPO_ROOT / "vnext/scripts/phase_exit_container_gate.sh").read_text(encoding="utf-8")
    assert "run_phase_exit_container_pytest" not in text
    assert "-m phase_exit_container" not in text
