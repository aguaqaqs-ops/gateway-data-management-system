"""Errors raised by the production Candidate A import provider adapter."""

from __future__ import annotations

import re
from typing import Any

_PRIVATE_REF_RE = re.compile(r"gateway-import-[0-9a-f]{32}", re.IGNORECASE)
_PATH_RE = re.compile(r"/[A-Za-z0-9_.:/-]+")
_STDERR_RE = re.compile(r"stderr\s*=\s*[^,\s}]+", re.IGNORECASE)
_SQL_STATEMENT_RE = re.compile(
    r"\bINSERT\s+INTO\b[^;]{0,200}|"
    r"\bUPDATE\s+\w+\s+SET\b[^;]{0,200}|"
    r"\bDELETE\s+FROM\b[^;]{0,200}|"
    r"\bSELECT\b.+\bFROM\b[^;]{0,200}",
    re.IGNORECASE | re.DOTALL,
)
_PRIMARY_KEY_VALUE_RE = re.compile(r"primary key \d+", re.IGNORECASE)
_VALUES_LITERAL_RE = re.compile(r"VALUES\s*\(\d+\)", re.IGNORECASE)
_QUOTED_STRING_RE = re.compile(r"'[^']*'|\"[^\"]*\"")
_MAX_DETAIL_LENGTH = 512


class ImportProviderError(RuntimeError):
    """Candidate A import provider execution or correctness failure."""


def sanitize_import_error_detail(detail: str | None) -> str | None:
    if detail is None:
        return None
    sanitized = _PRIVATE_REF_RE.sub("<private-ref>", detail)
    sanitized = _PATH_RE.sub("<path>", sanitized)
    sanitized = _STDERR_RE.sub("stderr=<redacted>", sanitized)
    sanitized = _SQL_STATEMENT_RE.sub("<sql>", sanitized)
    sanitized = _PRIMARY_KEY_VALUE_RE.sub("primary key <value>", sanitized)
    sanitized = _VALUES_LITERAL_RE.sub("VALUES (<value>)", sanitized)
    sanitized = _QUOTED_STRING_RE.sub("<value>", sanitized)
    if len(sanitized) > _MAX_DETAIL_LENGTH:
        return sanitized[:_MAX_DETAIL_LENGTH]
    return sanitized


def sanitize_import_error_details(details: dict[str, Any]) -> dict[str, object]:
    sanitized: dict[str, object] = {}
    for key, value in details.items():
        if isinstance(value, str):
            cleaned = sanitize_import_error_detail(value)
            sanitized[key] = cleaned if cleaned is not None else "<redacted>"
        elif isinstance(value, dict):
            sanitized[key] = sanitize_import_error_details(value)
        elif isinstance(value, list):
            sanitized[key] = [
                sanitize_import_error_details(item)
                if isinstance(item, dict)
                else sanitize_import_error_detail(str(item))
                if isinstance(item, str)
                else item
                for item in value
            ]
        else:
            sanitized[key] = value
    return sanitized
