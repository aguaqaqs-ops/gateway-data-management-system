"""PR-NATIVE: WP5 R4 rust-native required matrix cell on release wheel."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
from pathlib import Path

import gateway_compute.gateway_compute as native
import pytest

from gateway_conformance.harness.canonical_row_hashes.register import (
    register_production_canonical_row_hashes_harness,
)
from gateway_conformance.matrix import execute_formal_canonical_row_hash_matrix
from gateway_conformance.matrix.executor import discover_formal_scenario_root
from gateway_conformance.runner.registry import SubjectHarnessRegistry
from gateway_conformance.runner.runtime import LogicalClock
from gateway_conformance.paths import VNEXT_ROOT
from tests.runner_support import default_env_versions

pytestmark = pytest.mark.pr_native

REPO_ROOT = VNEXT_ROOT.parent
COMPUTE_PYTHON_ROOT = REPO_ROOT / "vnext" / "rust" / "gateway-compute-python"


def _require_gate_pr_native() -> None:
    if os.environ.get("GATE_PR_NATIVE") != "1":
        pytest.skip("PR-NATIVE matrix cell runs only under GATE_PR_NATIVE=1")


def _assert_release_wheel_loaded() -> None:
    module_file = Path(native.__file__).resolve()
    if str(module_file).startswith(str(COMPUTE_PYTHON_ROOT)):
        pytest.fail(f"extension must not load from source tree: {module_file}")
    dist = importlib.metadata.distribution("gateway-compute-python")
    direct_url = None
    for path in dist.files or []:
        if path.name == "direct_url.json":
            direct_url = json.loads(dist.locate_file(path).read_text(encoding="utf-8"))
            break
    if direct_url is None:
        pytest.fail("direct_url.json missing for gateway-compute-python")
    url = direct_url.get("url", "")
    if not url.endswith(".whl"):
        pytest.fail(f"expected wheel direct_url, got: {url}")
    if str(COMPUTE_PYTHON_ROOT) in url:
        pytest.fail(f"direct_url must not reference source tree: {url}")


def test_pr_native_rust_native_matrix_cell_passed() -> None:
    from gateway_conformance.runner.lifecycle import execute_scenario_run

    _require_gate_pr_native()
    _assert_release_wheel_loaded()
    before = hashlib.sha256(Path(native.__file__).read_bytes()).hexdigest()
    registry = SubjectHarnessRegistry()
    register_production_canonical_row_hashes_harness(registry)
    root = discover_formal_scenario_root()
    outcome = execute_scenario_run(
        root,
        profile="provider-matrix",
        provider_id="rust-native",
        run_id="wp5-r4-pr-native-rust-native",
        deterministic_seed="wp5-r4-pr-native",
        clock=LogicalClock("2026-01-01T00:00:00Z"),
        environment_versions=default_env_versions(),
        registry=registry,
    )
    result = outcome.result
    assert result["status"] == "PASSED"
    assert result["comparison_outcome"] == "MATCH"
    after = hashlib.sha256(Path(native.__file__).read_bytes()).hexdigest()
    assert before == after


def test_pr_native_full_matrix_on_wheel() -> None:
    _require_gate_pr_native()
    _assert_release_wheel_loaded()
    registry = SubjectHarnessRegistry()
    register_production_canonical_row_hashes_harness(registry)
    suite = execute_formal_canonical_row_hash_matrix(
        environment_versions=default_env_versions(),
        registry=registry,
        clock=LogicalClock("2026-01-01T00:00:00Z"),
    )
    assert suite.passed


def test_pr_native_mapping_provider_matrix_on_wheel() -> None:
    from gateway_conformance.harness.canonical_row_hashes.coverage_inventory import (
        assert_mapping_matrix_executed,
    )
    from gateway_conformance.harness.canonical_row_hashes.mapping_matrix import (
        run_mapping_provider_matrix,
    )

    _require_gate_pr_native()
    _assert_release_wheel_loaded()
    executed = run_mapping_provider_matrix()
    assert_mapping_matrix_executed(executed)
