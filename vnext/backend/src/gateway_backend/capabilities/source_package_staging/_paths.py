"""Package-internal path normalization and refusal."""

from __future__ import annotations

import re

from gateway_backend.capabilities.source_package_staging.contracts import (
    ResourceBudgets,
    StagingDiagnosticCode,
)

_WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:[\\/]")


class PathFault(Exception):
    def __init__(self, code: StagingDiagnosticCode, message: str, *, budget_name: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.budget_name = budget_name


def normalize_package_path(raw: str, budgets: ResourceBudgets) -> str:
    """Return a package-internal path starting with ``/``. Refuse host/traversal."""

    if type(raw) is not str or raw == "":
        raise PathFault(
            StagingDiagnosticCode.SOURCE_PACKAGE_INVALID,
            "package path must be a non-empty string",
        )
    if "\x00" in raw or "\\" in raw:
        raise PathFault(
            StagingDiagnosticCode.PATH_TRAVERSAL,
            "package path must not contain NUL or backslash",
        )
    lowered = raw.casefold()
    if raw.startswith("//") or lowered.startswith("file:") or _WINDOWS_DRIVE.match(raw) is not None:
        raise PathFault(
            StagingDiagnosticCode.PATH_TRAVERSAL,
            "package path must not be a host path",
        )
    stripped = raw[2:] if raw.startswith("./") else raw
    parts = stripped.split("/")
    if stripped.startswith("/"):
        parts = parts[1:]
    if parts == [""]:
        raise PathFault(
            StagingDiagnosticCode.SOURCE_PACKAGE_INVALID,
            "package path must not be empty",
        )
    if any(part == "" for part in parts):
        raise PathFault(
            StagingDiagnosticCode.PATH_TRAVERSAL,
            "package path must not contain empty segments",
        )
    if any(part in {".", ".."} for part in parts):
        raise PathFault(
            StagingDiagnosticCode.PATH_TRAVERSAL,
            "package path must not contain . or .. segments",
        )
    if len(parts) > budgets.max_path_segments:
        raise PathFault(
            StagingDiagnosticCode.RESOURCE_LIMIT_EXCEEDED,
            "package path exceeds max_path_segments",
            budget_name="max_path_segments",
        )
    normalized = "/" + "/".join(parts)
    if len(normalized.encode("utf-8")) > budgets.max_normalized_path_bytes:
        raise PathFault(
            StagingDiagnosticCode.RESOURCE_LIMIT_EXCEEDED,
            "package path exceeds max_normalized_path_bytes",
            budget_name="max_normalized_path_bytes",
        )
    return normalized
