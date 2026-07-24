"""Mutation probes for runner result assembly."""

from __future__ import annotations

import pytest

from gateway_conformance.errors import ConformanceValidationError
from gateway_conformance.protocol.validate import validate_runner_result_semantics
from gateway_conformance.runner.result import build_runner_result
from gateway_conformance.runner.types import ComparisonRow


def _base_plan() -> dict[str, object]:
    return {
        "execution_key": {
            "scenario_id": "data.test-capability.minimal",
            "profile": "reference",
            "provider_id": None,
            "fixture_content_digest": "sha256:" + "0" * 64,
        },
        "run_id": "run-mutation",
        "contract_bindings": [
            {
                "binding_id": "subject",
                "owner": "test-capability",
                "contract_id": "gateway-vnext.test-contract",
                "semantic_version": "1.0.0",
            }
        ],
    }


def test_build_runner_result_rejects_illegal_passed_shape() -> None:
    rows = [
        ComparisonRow(
            expectation_id="result",
            expected_content_digest="sha256:" + "0" * 64,
            actual_content_digest="sha256:" + "1" * 64,
            outcome="MATCH",
        )
    ]
    with pytest.raises(ConformanceValidationError):
        build_runner_result(
            plan=_base_plan(),
            rows=rows,
            unsupported=False,
            harness_error=False,
            cleanup="CLEAN",
            diagnostics=[],
        )


def test_semantic_validator_blocks_fifth_status() -> None:
    result = {
        "runner_result_schema_version": 1,
        "execution_key": _base_plan()["execution_key"],
        "run_id": "run-mutation",
        "contract_bindings": _base_plan()["contract_bindings"],
        "status": "BLOCKED",
        "comparison_outcome": "NOT_RUN",
        "expectations": [
            {
                "expectation_id": "result",
                "expected_content_digest": "sha256:" + "0" * 64,
                "actual_content_digest": None,
                "outcome": "NOT_RUN",
            }
        ],
        "evidence_ref": None,
        "cleanup": {"status": "CLEAN", "diagnostics": []},
        "diagnostics": [],
    }
    with pytest.raises(ConformanceValidationError):
        validate_runner_result_semantics(result)
