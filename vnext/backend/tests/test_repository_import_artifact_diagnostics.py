"""Submit import publication projection failure formatting."""

from __future__ import annotations

import pytest

from gateway_backend.capabilities.storage_projection import (
    ProjectionDiagnostic,
    ProjectionDiagnosticCode,
    ProjectionDiagnosticSeverity,
)
from gateway_backend.application.submission.errors import SubmitImportPublicationError
from gateway_backend.repository_import_artifact import _format_projection_diagnostics

pytestmark = pytest.mark.unit


def test_format_projection_diagnostics_includes_code_message_and_table() -> None:
    message = _format_projection_diagnostics(
        "storage projection failed",
        (
            ProjectionDiagnostic(
                code=ProjectionDiagnosticCode.UNSUPPORTED_TABLE,
                severity=ProjectionDiagnosticSeverity.ERROR,
                message="column scalar_type is not supported",
                table_name="t3",
            ),
        ),
    )
    assert message == (
        "storage projection failed: UNSUPPORTED_TABLE: "
        "column scalar_type is not supported (table=t3)"
    )


def test_format_projection_diagnostics_summarizes_additional_items() -> None:
    message = _format_projection_diagnostics(
        "storage projection failed",
        (
            ProjectionDiagnostic(
                code=ProjectionDiagnosticCode.UNSUPPORTED_TABLE,
                severity=ProjectionDiagnosticSeverity.ERROR,
                message="column scalar_type is not supported",
                table_name="t3",
            ),
            ProjectionDiagnostic(
                code=ProjectionDiagnosticCode.UNSUPPORTED_TABLE,
                severity=ProjectionDiagnosticSeverity.ERROR,
                message="column scalar_type is not supported",
                table_name="t4",
            ),
            ProjectionDiagnostic(
                code=ProjectionDiagnosticCode.UNSUPPORTED_TABLE,
                severity=ProjectionDiagnosticSeverity.ERROR,
                message="column scalar_type is not supported",
                table_name="t5",
            ),
        ),
    )
    assert "UNSUPPORTED_TABLE: column scalar_type is not supported (table=t3)" in message
    assert "also=UNSUPPORTED_TABLE:column scalar_type is not supported@t4" in message
    assert "@t5" in message


def test_submit_import_publication_error_uses_projection_diagnostic_format() -> None:
    error = SubmitImportPublicationError(
        _format_projection_diagnostics(
            "storage projection failed",
            (
                ProjectionDiagnostic(
                    code=ProjectionDiagnosticCode.UNSUPPORTED_TABLE,
                    severity=ProjectionDiagnosticSeverity.ERROR,
                    message="column scalar_type is not supported",
                    table_name="b1_n1_iec104_syx_list",
                ),
            ),
        )
    )
    text = str(error)
    assert "UNSUPPORTED_TABLE" in text
    assert "column scalar_type is not supported" in text
    assert "table=b1_n1_iec104_syx_list" in text
