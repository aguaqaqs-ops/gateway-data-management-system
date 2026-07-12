from __future__ import annotations

import re
from pathlib import PurePosixPath
from collections.abc import Mapping

from ...core.validation import require_non_empty


_WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:[\\/]")
_FORBIDDEN_SURFACE_OPTION_KEYS = {
    "surface_id",
    "view_id",
    "view_label",
    "surface_ref",
    "records_closure_ref",
    "risk_report_ref",
    "risk_annotation_closure_ref",
    "diagnostics_ref",
    "preview_bundle_id",
    "preview_revision_id",
    "workspace_id",
    "submission_id",
    "history_request_id",
    "submit_binding",
    "target_set_binding",
    "repository_commit_hash",
    "host_path",
    "cache_ref",
}


def ensure_logical_relative_ref(value: str, field_name: str) -> None:
    require_non_empty(value, field_name)
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"{field_name} must be relative to the bundle root")
    if "://" in value:
        raise ValueError(f"{field_name} must not be a URL or URI")
    if _WINDOWS_DRIVE_RE.match(value) is not None:
        raise ValueError(f"{field_name} must not be an absolute host path")


def ensure_logical_relative_refs(values: tuple[str, ...], field_name: str) -> None:
    for value in values:
        ensure_logical_relative_ref(value, field_name)


def ensure_surface_options(surface_options: Mapping[str, object]) -> None:
    for key in surface_options:
        if key in _FORBIDDEN_SURFACE_OPTION_KEYS:
            raise ValueError(f"surface_options must not contain {key}")
