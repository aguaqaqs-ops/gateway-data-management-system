"""Tests for Versioned import error detail sanitization."""

from __future__ import annotations

import pytest

from gateway_repository_service.versioned_import.errors import sanitize_import_error_detail


@pytest.mark.parametrize(
    ("detail", "forbidden"),
    [
        ("duplicate primary key value 42", ("42",)),
        ("row 99 conflicts with existing row 100", ("99", "100")),
        ("constraint violation on column age value 37", ("37",)),
        ("replay failed at line 4211: value 88 out of range for column salary", ("4211", "88")),
        (
            "command failed: dolt sql exit=1 stderr=Error: table users column email value bob@corp.internal",
            ("bob@corp.internal",),
        ),
    ],
)
def test_sanitize_import_error_detail_redacts_sensitive_tokens(
    detail: str,
    forbidden: tuple[str, ...],
) -> None:
    sanitized = sanitize_import_error_detail(detail)
    assert sanitized is not None
    for token in forbidden:
        assert token not in sanitized


def test_sanitize_import_error_detail_preserves_readable_identifiers() -> None:
    message = "update of main ref did not apply"
    sanitized = sanitize_import_error_detail(message)
    assert sanitized is not None
    assert "update" in sanitized
    assert "main" in sanitized


def test_sanitize_import_error_detail_preserves_quoted_ref_names() -> None:
    message = "failed to read ref 'main' points to def456"
    sanitized = sanitize_import_error_detail(message)
    assert sanitized is not None
    assert "'main'" in sanitized or "main" in sanitized


def test_sanitize_import_error_detail_redacts_stderr_tail() -> None:
    message = (
        "command failed: dolt sql exit=1 stderr=b'error: duplicate primary key 42; "
        "near INSERT INTO records VALUES (42)'"
    )
    sanitized = sanitize_import_error_detail(message)
    assert sanitized is not None
    assert "INSERT INTO" not in sanitized
    assert "42" not in sanitized
    assert "stderr=<redacted>" in sanitized
