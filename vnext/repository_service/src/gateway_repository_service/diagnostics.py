"""Minimal structured diagnostics for Repository Service operational events."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any
from uuid import UUID

_LOGGER = logging.getLogger("gateway_repository_service.diagnostics")

_ALLOWED_KEYS = frozenset(
    {
        "event",
        "request_id",
        "repository_id",
        "operation_id",
        "artifact_id",
        "stage",
        "duration_ms",
        "size_bytes",
        "result",
        "code",
        "capacity",
        "in_use",
        "cleanup_outcome",
        "max_concurrent_uploads",
        "max_concurrent_row_streams",
        "max_import_workers",
        "max_queued_imports",
        "artifact_ttl_seconds",
        "artifact_cleanup_interval_seconds",
        "artifact_tombstone_budget",
        "full_scan_timeout_seconds",
        "min_free_disk_bytes",
        "min_free_disk_fraction",
        "import_headroom_bytes",
    }
)

_FORBIDDEN_SUBSTRINGS = (
    "bearer",
    "token",
    "idempotency",
    "authorization",
    "password",
    "secret",
    "stderr",
    "sql",
    "query_string",
    "private_ref",
)


def operational_limits(settings: Mapping[str, Any] | object) -> dict[str, Any]:
    """Return a redacted subset of operational limits safe for startup logs."""
    if hasattr(settings, "model_dump"):
        data = settings.model_dump()
    elif isinstance(settings, Mapping):
        data = dict(settings)
    else:
        data = {
            name: getattr(settings, name)
            for name in (
                "max_concurrent_uploads",
                "max_concurrent_row_streams",
                "max_import_workers",
                "max_queued_imports",
                "artifact_ttl_seconds",
                "artifact_cleanup_interval_seconds",
                "artifact_tombstone_budget",
                "full_scan_timeout_seconds",
                "min_free_disk_bytes",
                "min_free_disk_fraction",
                "import_headroom_bytes",
            )
            if hasattr(settings, name)
        }
    allowed = {
        "max_concurrent_uploads",
        "max_concurrent_row_streams",
        "max_import_workers",
        "max_queued_imports",
        "artifact_ttl_seconds",
        "artifact_cleanup_interval_seconds",
        "artifact_tombstone_budget",
        "full_scan_timeout_seconds",
        "min_free_disk_bytes",
        "min_free_disk_fraction",
        "import_headroom_bytes",
    }
    return {key: data[key] for key in allowed if key in data}


def _opaque_id(value: UUID | str | None) -> str | None:
    if value is None:
        return None
    return str(value)


def log_event(
    event: str,
    *,
    level: int = logging.INFO,
    request_id: str | None = None,
    repository_id: UUID | str | None = None,
    operation_id: UUID | str | None = None,
    artifact_id: UUID | str | None = None,
    stage: str | None = None,
    duration_ms: int | float | None = None,
    size_bytes: int | None = None,
    result: str | None = None,
    code: str | None = None,
    capacity: int | None = None,
    in_use: int | None = None,
    cleanup_outcome: str | None = None,
    extra_fields: Mapping[str, Any] | None = None,
    logger: logging.Logger | None = None,
) -> None:
    """Emit a structured operational event with stable fields only.

    Fail-safe: logger or payload errors must never alter public request results.
    """
    try:
        payload: dict[str, Any] = {"event": event}
        if request_id is not None:
            payload["request_id"] = request_id
        for key, value in (
            ("repository_id", _opaque_id(repository_id)),
            ("operation_id", _opaque_id(operation_id)),
            ("artifact_id", _opaque_id(artifact_id)),
            ("stage", stage),
            ("duration_ms", duration_ms),
            ("size_bytes", size_bytes),
            ("result", result),
            ("code", code),
            ("capacity", capacity),
            ("in_use", in_use),
            ("cleanup_outcome", cleanup_outcome),
        ):
            if value is not None:
                payload[key] = value
        if extra_fields:
            for key, value in extra_fields.items():
                lowered = key.lower()
                if key not in _ALLOWED_KEYS or any(part in lowered for part in _FORBIDDEN_SUBSTRINGS):
                    continue
                if value is None:
                    continue
                payload[key] = value

        target = logger or _LOGGER
        target.log(level, event, extra={"gateway_fields": payload, **payload})
    except Exception:
        return
