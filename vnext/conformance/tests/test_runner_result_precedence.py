"""Result precedence oracle and end-to-end status tests."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import pytest

from gateway_conformance.runner.fake.harness import FakeSubjectHarness
from gateway_conformance.runner.lifecycle import execute_scenario_run
from gateway_conformance.runner.registry import SubjectHarnessRegistry
from gateway_conformance.errors import ConformanceValidationError
from gateway_conformance.runner.result import apply_recovery_checkpoint_gate, resolve_final_status
from gateway_conformance.runner.types import ComparisonRow
from gateway_conformance.runner.runtime import LogicalClock
from tests.runner_support import default_env_versions, register_fake_harness
from tests.runner_support import build_data_scenario

# Independent precedence oracle (not calling validate_runner_result_semantics).
_ORACLE: dict[tuple[bool, bool, str, str], str] = {
    (True, False, "NOT_RUN", "CLEAN"): "UNSUPPORTED",
    (True, True, "NOT_RUN", "CLEAN"): "HARNESS_ERROR",
    (False, True, "MATCH", "CLEAN"): "HARNESS_ERROR",
    (False, True, "NOT_RUN", "CLEAN"): "HARNESS_ERROR",
    (False, False, "NOT_RUN", "CLEAN"): "HARNESS_ERROR",
    (False, False, "MATCH", "CLEAN"): "PASSED",
    (False, False, "MISMATCH", "CLEAN"): "ASSERTION_FAILED",
    (False, False, "MATCH", "LEAKED"): "HARNESS_ERROR",
    (False, False, "MISMATCH", "LEAKED"): "HARNESS_ERROR",
}


@pytest.mark.parametrize(
    ("unsupported", "harness_error", "comparison", "cleanup", "expected"),
    [
        (True, False, "NOT_RUN", "CLEAN", "UNSUPPORTED"),
        (True, True, "NOT_RUN", "CLEAN", "HARNESS_ERROR"),
        (False, True, "MATCH", "CLEAN", "HARNESS_ERROR"),
        (False, False, "MATCH", "CLEAN", "PASSED"),
        (False, False, "MISMATCH", "CLEAN", "ASSERTION_FAILED"),
        (False, False, "MATCH", "LEAKED", "HARNESS_ERROR"),
        (False, False, "MISMATCH", "LEAKED", "HARNESS_ERROR"),
    ],
)
def test_resolve_final_status_matches_independent_oracle(
    unsupported: bool,
    harness_error: bool,
    comparison: Literal["NOT_RUN", "MATCH", "MISMATCH"],
    cleanup: Literal["CLEAN", "LEAKED", "FAILED"],
    expected: str,
) -> None:
    key = (unsupported, harness_error, comparison, cleanup)
    assert _ORACLE[key] == expected
    assert (
        resolve_final_status(
            unsupported=unsupported,
            harness_error=harness_error,
            comparison=comparison,
            cleanup=cleanup,
        )
        == expected
    )


def test_end_to_end_four_states(tmp_path: Path) -> None:
    root = build_data_scenario(tmp_path)

    registry = SubjectHarnessRegistry()
    register_fake_harness(registry)
    passed = execute_scenario_run(
        root,
        profile="reference",
        provider_id=None,
        run_id="run-pass",
        deterministic_seed="seed",
        clock=LogicalClock("2026-01-01T00:00:00Z"),
        environment_versions=default_env_versions(),
        registry=registry,
    )
    assert passed.result["status"] == "PASSED"

    registry = SubjectHarnessRegistry()
    register_fake_harness(
        registry,
        factory=lambda: FakeSubjectHarness(observation_mode="mismatch"),
    )
    failed = execute_scenario_run(
        root,
        profile="reference",
        provider_id=None,
        run_id="run-fail",
        deterministic_seed="seed",
        clock=LogicalClock("2026-01-01T00:00:00Z"),
        environment_versions=default_env_versions(),
        registry=registry,
    )
    assert failed.result["status"] == "ASSERTION_FAILED"

    registry = SubjectHarnessRegistry()
    register_fake_harness(
        registry,
        factory=lambda: FakeSubjectHarness(preflight_behavior="unsupported"),
    )
    unsupported = execute_scenario_run(
        root,
        profile="reference",
        provider_id=None,
        run_id="run-unsup",
        deterministic_seed="seed",
        clock=LogicalClock("2026-01-01T00:00:00Z"),
        environment_versions=default_env_versions(),
        registry=registry,
    )
    assert unsupported.result["status"] == "UNSUPPORTED"

    registry = SubjectHarnessRegistry()
    register_fake_harness(
        registry,
        factory=lambda: FakeSubjectHarness(observation_mode="missing"),
    )
    harness_error = execute_scenario_run(
        root,
        profile="reference",
        provider_id=None,
        run_id="run-herr",
        deterministic_seed="seed",
        clock=LogicalClock("2026-01-01T00:00:00Z"),
        environment_versions=default_env_versions(),
        registry=registry,
    )
    assert harness_error.result["status"] == "HARNESS_ERROR"


def test_unsupported_with_harness_error_prefers_harness_error() -> None:
    assert (
        resolve_final_status(
            unsupported=True,
            harness_error=True,
            comparison="NOT_RUN",
            cleanup="CLEAN",
        )
        == "HARNESS_ERROR"
    )


def test_checkpoint_gate_rejects_equal_expected_and_mismatch_digest() -> None:
    digest = "sha256:" + "a" * 64
    rows = [
        ComparisonRow(
            expectation_id="result",
            expected_content_digest=digest,
            actual_content_digest=digest,
            outcome="MATCH",
        )
    ]
    with pytest.raises(ConformanceValidationError, match="must differ"):
        apply_recovery_checkpoint_gate(
            rows,
            [],
            expectation_digests={"result": digest},
            mismatch_expectation_ids={"result"},
        )
