"""Ref, marker, and commit-id validation for Candidate A versioned import."""

from __future__ import annotations

import re
from typing import Any
from uuid import UUID

IMPORT_MAIN_REF = "main"
IMPORT_PRIVATE_REF_PATTERN = re.compile(r"^gateway-import-[0-9a-f]{32}$")
IMPORT_OPERATION_MARKER_PATTERN = re.compile(
    r"^gateway-versioned-import operation_id="
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)
COMMIT_ID_PATTERN = re.compile(r"^[0-9a-zA-Z_-]+$")


def validate_readable_ref_name(ref_name: str) -> str:
    if ref_name == IMPORT_MAIN_REF:
        return ref_name
    if IMPORT_PRIVATE_REF_PATTERN.fullmatch(ref_name):
        return ref_name
    raise ValueError("import ref name is invalid")


def validate_private_ref_name(private_ref: str) -> str:
    if not IMPORT_PRIVATE_REF_PATTERN.fullmatch(private_ref):
        raise ValueError("import private ref name is invalid")
    return private_ref


def validate_operation_marker(marker: str) -> str:
    if IMPORT_OPERATION_MARKER_PATTERN.fullmatch(marker):
        return marker
    raise ValueError("operation marker is invalid")


def parse_operation_id_from_private_ref(private_ref: str) -> UUID:
    safe_ref = validate_private_ref_name(private_ref)
    return UUID(hex=safe_ref.removeprefix("gateway-import-"))


def parse_operation_id_from_marker(marker: str) -> UUID:
    safe_marker = validate_operation_marker(marker)
    return UUID(safe_marker.split("=", 1)[1])


def validate_private_ref_marker_pair(private_ref: str, marker: str) -> None:
    ref_operation = parse_operation_id_from_private_ref(private_ref)
    marker_operation = parse_operation_id_from_marker(marker)
    if ref_operation != marker_operation:
        raise ValueError("private ref and marker operation id mismatch")


def validate_commit_id(commit_id: str) -> str:
    if not COMMIT_ID_PATTERN.fullmatch(commit_id):
        raise ValueError("commit id is invalid")
    return commit_id


def opaque_commit_literal(commit_id: str) -> str:
    """Encode an opaque commit token as an unambiguous UTF-8 SQL expression."""

    if commit_id == "":
        return "''"
    byte_codes = ",".join(str(byte) for byte in commit_id.encode("utf-8"))
    return f"CONCAT(CHAR({byte_codes}))"


def commit_literal(commit_id: str) -> str:
    return opaque_commit_literal(validate_commit_id(commit_id))


def marker_literal(marker: str) -> str:
    return "'" + validate_operation_marker(marker).replace("'", "''") + "'"


def parse_single_parent(parents_field: str) -> str | None:
    parents = [part.strip() for part in parents_field.split(",") if part.strip()]
    if len(parents) != 1:
        return None
    return parents[0]


def parse_log_parent_field(raw: Any) -> str | None:
    if raw is None or not isinstance(raw, str) or not raw.strip():
        return None
    parent = parse_single_parent(raw.strip())
    if parent is None:
        return None
    return validate_commit_id(parent)


def parse_marker_parent_field(raw: str) -> str | None:
    if "," in raw:
        return None
    if raw != raw.strip():
        return None
    try:
        return validate_commit_id(raw)
    except ValueError:
        return None
