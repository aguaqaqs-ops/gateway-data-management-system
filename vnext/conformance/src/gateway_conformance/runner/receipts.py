"""Closed-set validation for harness receipts and support decisions."""

from __future__ import annotations

import re

from gateway_conformance.errors import ConformanceValidationError
from gateway_conformance.scenario.identity import assert_lower_kebab
from gateway_conformance.runner.diagnostics import sanitize_diagnostic
from gateway_conformance.runner.types import (
    CleanupReceipt,
    CleanupStatus,
    Diagnostic,
    PhaseName,
    PhaseReceipt,
    SupportDecision,
)

_STABLE_CODE_RE = re.compile(r"^[a-z][a-z0-9-]*$")
_VALID_OUTCOMES = frozenset({"COMPLETED", "FAILED"})
_VALID_SUPPORT = frozenset({"SUPPORTED", "UNSUPPORTED"})
_VALID_CLEANUP: frozenset[CleanupStatus] = frozenset({"CLEAN", "LEAKED", "FAILED"})


def _validate_diagnostics(diagnostics: tuple[Diagnostic, ...]) -> None:
    for item in diagnostics:
        if not str(item.code).strip():
            raise ConformanceValidationError("diagnostic code must be non-empty")
        if not str(item.message).strip():
            raise ConformanceValidationError("diagnostic message must be non-empty")
        assert_lower_kebab(str(item.code), label="diagnostic.code")


def _validate_stable_code(stable_code: str | None) -> None:
    if stable_code is None or stable_code == "":
        raise ConformanceValidationError("FAILED receipt requires stable_code")
    if not _STABLE_CODE_RE.fullmatch(stable_code):
        raise ConformanceValidationError("stable_code must be lower-kebab token")


def validate_support_decision(decision: SupportDecision) -> None:
    if decision.support not in _VALID_SUPPORT:
        raise ConformanceValidationError("invalid preflight support value")
    _validate_diagnostics(decision.diagnostics)
    if decision.support == "UNSUPPORTED":
        if not decision.reason_code or not str(decision.reason_code).strip():
            raise ConformanceValidationError("UNSUPPORTED requires reason_code")
        assert_lower_kebab(str(decision.reason_code), label="reason_code")


def validate_phase_receipt(receipt: PhaseReceipt, expected_phase: PhaseName) -> None:
    if receipt.phase != expected_phase:
        raise ConformanceValidationError(f"receipt phase mismatch: {receipt.phase}")
    if receipt.outcome not in _VALID_OUTCOMES:
        raise ConformanceValidationError(f"invalid receipt outcome: {receipt.outcome}")
    _validate_diagnostics(receipt.diagnostics)
    if receipt.outcome == "COMPLETED":
        if receipt.stable_code is not None and receipt.stable_code != "":
            raise ConformanceValidationError("COMPLETED receipt must not include stable_code")
        return
    _validate_stable_code(receipt.stable_code)


def validate_cleanup_receipt(receipt: CleanupReceipt) -> None:
    if receipt.status not in _VALID_CLEANUP:
        raise ConformanceValidationError(f"invalid cleanup status: {receipt.status}")
    _validate_diagnostics(receipt.diagnostics)


def receipt_diagnostics_for_state(
    receipt: PhaseReceipt | SupportDecision,
    *,
    prefix: str,
) -> list[Diagnostic]:
    items = receipt.diagnostics
    return [
        sanitize_diagnostic(
            Diagnostic(code=f"{prefix}-{item.code}", message=item.message),
        )
        for item in items
    ]
