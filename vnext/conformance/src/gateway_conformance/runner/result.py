"""Runner result aggregation and precedence."""

from __future__ import annotations

from typing import Any, Literal

from gateway_conformance.errors import ConformanceValidationError
from gateway_conformance.protocol.validate import validate_runner_result_semantics
from gateway_conformance.runner.types import CleanupStatus, ComparisonRow, Diagnostic
from gateway_conformance.sanitize import sanitize_message


ComparisonOutcome = Literal["NOT_RUN", "MATCH", "MISMATCH"]
RunnerStatus = Literal["PASSED", "ASSERTION_FAILED", "HARNESS_ERROR", "UNSUPPORTED"]


def aggregate_comparison_outcome(
    outcomes: list[Literal["NOT_RUN", "MATCH", "MISMATCH"]],
) -> ComparisonOutcome:
    if "MISMATCH" in outcomes:
        return "MISMATCH"
    if "MATCH" in outcomes:
        return "MATCH"
    return "NOT_RUN"


def resolve_final_status(
    *,
    unsupported: bool,
    harness_error: bool,
    comparison: ComparisonOutcome,
    cleanup: CleanupStatus,
) -> RunnerStatus:
    if harness_error:
        return "HARNESS_ERROR"
    if unsupported:
        return "UNSUPPORTED"
    if comparison == "NOT_RUN":
        return "HARNESS_ERROR"
    if cleanup != "CLEAN":
        return "HARNESS_ERROR"
    if comparison == "MATCH":
        return "PASSED"
    return "ASSERTION_FAILED"


def build_not_run_expectations(manifest: dict[str, Any]) -> list[ComparisonRow]:
    rows: list[ComparisonRow] = []
    for entry in manifest["expected"]:
        expectation_id = str(entry["expectation_id"])
        rows.append(
            ComparisonRow(
                expectation_id=expectation_id,
                expected_content_digest=str(entry["content_digest"]),
                actual_content_digest=None,
                outcome="NOT_RUN",
            )
        )
    rows.sort(key=lambda item: item.expectation_id)
    return rows


def apply_recovery_checkpoint_gate(
    rows: list[ComparisonRow],
    checkpoint_results: list[dict[str, Any]],
    *,
    expectation_digests: dict[str, str] | None = None,
    mismatch_expectation_ids: set[str] | None = None,
) -> list[ComparisonRow]:
    mismatch_ids = set(mismatch_expectation_ids or ())
    if not mismatch_ids:
        return rows
    per_id = dict(expectation_digests or {})
    gated: list[ComparisonRow] = []
    for row in rows:
        if row.expectation_id not in mismatch_ids:
            gated.append(row)
            continue
        mismatch_digest = per_id.get(row.expectation_id)
        if mismatch_digest is None:
            raise ConformanceValidationError(
                "recovery checkpoint gate missing digest for expectation"
            )
        if mismatch_digest == row.expected_content_digest:
            raise ConformanceValidationError(
                "recovery checkpoint gate digest must differ from expected for MISMATCH"
            )
        gated.append(
            ComparisonRow(
                expectation_id=row.expectation_id,
                expected_content_digest=row.expected_content_digest,
                actual_content_digest=mismatch_digest,
                outcome="MISMATCH",
            )
        )
    return gated


def build_runner_result(
    *,
    plan: dict[str, Any],
    rows: list[ComparisonRow],
    unsupported: bool,
    harness_error: bool,
    cleanup: CleanupStatus,
    diagnostics: list[Diagnostic],
    cleanup_diagnostics: list[Diagnostic] | None = None,
) -> dict[str, Any]:
    if unsupported and harness_error:
        unsupported = False
        harness_error = True
    sanitized_runner = [
        Diagnostic(code=item.code, message=sanitize_message(item.message)[:500])
        for item in diagnostics
    ]
    sanitized_cleanup = [
        Diagnostic(code=item.code, message=sanitize_message(item.message)[:500])
        for item in (cleanup_diagnostics or [])
    ]
    outcomes = [row.outcome for row in rows]
    comparison = aggregate_comparison_outcome(outcomes)
    status = resolve_final_status(
        unsupported=unsupported,
        harness_error=harness_error,
        comparison=comparison,
        cleanup=cleanup,
    )
    if unsupported:
        comparison = "NOT_RUN"
    expectations = [
        {
            "expectation_id": row.expectation_id,
            "expected_content_digest": row.expected_content_digest,
            "actual_content_digest": row.actual_content_digest,
            "outcome": row.outcome,
        }
        for row in sorted(rows, key=lambda item: item.expectation_id)
    ]
    result: dict[str, Any] = {
        "runner_result_schema_version": 1,
        "execution_key": dict(plan["execution_key"]),
        "run_id": str(plan["run_id"]),
        "contract_bindings": [dict(item) for item in plan["contract_bindings"]],
        "status": status,
        "comparison_outcome": comparison,
        "expectations": expectations,
        "evidence_ref": None,
        "cleanup": {
            "status": cleanup,
            "diagnostics": [item.to_wire() for item in sanitized_cleanup],
        },
        "diagnostics": [item.to_wire() for item in sanitized_runner],
    }
    validate_runner_result_semantics(result)
    return result
